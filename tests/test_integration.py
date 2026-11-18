"""End-to-end tests against a real (test) Home Assistant instance."""

import asyncio

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
)

from homeassistant import config_entries
from homeassistant.const import STATE_HOME, STATE_NOT_HOME, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.setup import async_setup_component

from custom_components.shape_zones.const import (
    CONF_MARGIN,
    CONF_MAX_ACCURACY,
    CONF_TRACKERS,
    CONF_ZONES,
    DOMAIN,
    EVENT_ENTER,
    EVENT_LEAVE,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

SOURCE = "device_tracker.phone"
TRACKER = "device_tracker.shape_zones_phone"
SENSOR = "binary_sensor.shape_zones_winkel"

# The test instance's home is at 32.87336, -117.22743 (radius 100 m).
SHOP = [[32.8800, -117.2310], [32.8800, -117.2290], [32.8810, -117.2290], [32.8810, -117.2310]]
IN_SHOP = (32.8805, -117.2300)
FAR_AWAY = (32.9000, -117.2000)
HOME = (32.87336, -117.22743)


async def settle(hass: HomeAssistant) -> None:
    """Let state changes that trigger further state changes run through.

    Our tracker writes its state from inside the source tracker's state-change
    event; HA delivers that second event one loop iteration later.
    """
    for _ in range(3):
        await hass.async_block_till_done()
        await asyncio.sleep(0)


def set_source(hass: HomeAssistant, lat: float, lon: float, accuracy: float = 10) -> None:
    hass.states.async_set(
        SOURCE,
        STATE_NOT_HOME,
        {"latitude": lat, "longitude": lon, "gps_accuracy": accuracy,
         "source_type": "gps", "friendly_name": "Phone"},
    )


async def setup_entry(hass: HomeAssistant, **options) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Shape Zones",
        options={
            CONF_ZONES: [{"id": "shop", "name": "Winkel", "icon": "mdi:store", "points": SHOP}],
            CONF_TRACKERS: [SOURCE],
            CONF_MAX_ACCURACY: 100,
            CONF_MARGIN: 10,
            **options,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await settle(hass)
    return entry


async def test_tracker_and_person_show_shape_zone(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, "zone", {})
    set_source(hass, *FAR_AWAY)
    await setup_entry(hass)
    assert await async_setup_component(
        hass, "person",
        {"person": [{"id": "jordi", "name": "Jordi", "device_trackers": [TRACKER]}]},
    )
    await settle(hass)

    assert hass.states.get(TRACKER).state == STATE_NOT_HOME
    assert hass.states.get(SENSOR).state == STATE_OFF

    set_source(hass, *IN_SHOP)
    await settle(hass)
    tracker = hass.states.get(TRACKER)
    assert tracker.state == "Winkel"
    assert tracker.attributes["latitude"] == IN_SHOP[0]
    assert hass.states.get("person.jordi").state == "Winkel"
    sensor = hass.states.get(SENSOR)
    assert sensor.state == STATE_ON
    assert sensor.attributes["count"] == 1
    assert sensor.attributes["names"] == ["Phone"]

    # outside the shape zones, normal HA zones still apply
    set_source(hass, *HOME)
    await settle(hass)
    assert hass.states.get(TRACKER).state == STATE_HOME
    assert hass.states.get("person.jordi").state == STATE_HOME
    assert hass.states.get(SENSOR).state == STATE_OFF


async def test_enter_and_leave_events(hass: HomeAssistant) -> None:
    set_source(hass, *FAR_AWAY)
    await setup_entry(hass)
    enters = async_capture_events(hass, EVENT_ENTER)
    leaves = async_capture_events(hass, EVENT_LEAVE)

    set_source(hass, *IN_SHOP)
    await settle(hass)
    set_source(hass, *FAR_AWAY)
    await settle(hass)

    assert [e.data["zone"] for e in enters] == ["Winkel"]
    assert [e.data["zone"] for e in leaves] == ["Winkel"]
    assert enters[0].data["entity_id"] == TRACKER
    assert enters[0].data["source"] == SOURCE


async def test_no_events_at_startup(hass: HomeAssistant) -> None:
    set_source(hass, *IN_SHOP)
    enters = async_capture_events(hass, EVENT_ENTER)
    await setup_entry(hass)
    assert hass.states.get(TRACKER).state == "Winkel"
    assert enters == []


async def test_inaccurate_fix_does_not_change_zone(hass: HomeAssistant) -> None:
    set_source(hass, *IN_SHOP)
    await setup_entry(hass)
    set_source(hass, *FAR_AWAY, accuracy=500)
    await settle(hass)
    assert hass.states.get(TRACKER).state == "Winkel"
    set_source(hass, *FAR_AWAY, accuracy=20)
    await settle(hass)
    assert hass.states.get(TRACKER).state == STATE_NOT_HOME


async def test_margin_at_the_edge(hass: HomeAssistant) -> None:
    set_source(hass, *IN_SHOP)
    await setup_entry(hass)
    set_source(hass, 32.88105, -117.2300)  # ~5.5 m north of the shop
    await settle(hass)
    assert hass.states.get(TRACKER).state == "Winkel"
    set_source(hass, 32.8812, -117.2300)  # ~22 m north
    await settle(hass)
    assert hass.states.get(TRACKER).state == STATE_NOT_HOME


async def test_source_without_gps_is_passed_through(hass: HomeAssistant) -> None:
    hass.states.async_set(SOURCE, STATE_HOME, {"source_type": "router", "friendly_name": "Phone"})
    await setup_entry(hass)
    assert hass.states.get(TRACKER).state == STATE_HOME


async def test_config_flow_and_options(hass: HomeAssistant) -> None:
    set_source(hass, *IN_SHOP)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TRACKERS: [SOURCE]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await settle(hass)
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert hass.states.get(TRACKER).state == STATE_NOT_HOME

    # add a zone: two corners -> rectangle
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "add_zone"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"name": "Winkel", "coordinates": "32.8800, -117.2310\n32.8810, -117.2290"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await settle(hass)
    assert hass.states.get(TRACKER).state == "Winkel"
    assert hass.states.get(SENSOR).state == STATE_ON

    # duplicate name and bad coordinates are rejected
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "add_zone"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"name": "winkel", "coordinates": "32.88"}
    )
    assert result["errors"] == {"name": "name_exists", "coordinates": "uneven_numbers"}

    # our own tracker can't be followed
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "trackers"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_TRACKERS: [TRACKER]}
    )
    assert result["errors"] == {CONF_TRACKERS: "own_tracker"}

    # edit the zone so the phone is no longer inside
    zone_id = entry.options[CONF_ZONES][0]["id"]
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "pick_zone"}
    )
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"zone_id": zone_id})
    assert result["step_id"] == "edit_zone"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"name": "Winkel", "coordinates": "32.8900, -117.2310\n32.8910, -117.2290"}
    )
    await settle(hass)
    assert hass.states.get(TRACKER).state == STATE_NOT_HOME

    # remove it: the sensor entity disappears
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "remove_zones"}
    )
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"zones": [zone_id]})
    await settle(hass)
    assert hass.states.get(SENSOR) is None
