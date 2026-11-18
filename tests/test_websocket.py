"""Tests for the websocket API behind the map panel."""

from homeassistant.core import HomeAssistant
import pytest

from custom_components.shape_zones.const import CONF_ZONES

from .test_integration import IN_SHOP, SENSOR, SHOP, TRACKER, set_source, settle, setup_entry

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


async def test_get_save_delete(hass: HomeAssistant, hass_ws_client) -> None:
    set_source(hass, *IN_SHOP)
    entry = await setup_entry(hass, **{CONF_ZONES: []})
    client = await hass_ws_client(hass)

    await client.send_json_auto_id({"type": "shape_zones/get"})
    msg = await client.receive_json()
    assert msg["success"]
    assert msg["result"] == {"zones": [], "trackers": [TRACKER]}

    await client.send_json_auto_id(
        {"type": "shape_zones/save_zone", "name": "Winkel", "points": SHOP}
    )
    msg = await client.receive_json()
    assert msg["success"], msg
    zone_id = msg["result"]["id"]
    await settle(hass)
    assert hass.states.get(TRACKER).state == "Winkel"
    assert hass.states.get(SENSOR).state == "on"

    # same name (other case) is refused
    await client.send_json_auto_id(
        {"type": "shape_zones/save_zone", "name": "winkel", "points": SHOP}
    )
    msg = await client.receive_json()
    assert msg["error"]["code"] == "name_exists"

    # too few points is refused by the schema
    await client.send_json_auto_id(
        {"type": "shape_zones/save_zone", "name": "X", "points": SHOP[:2]}
    )
    assert not (await client.receive_json())["success"]

    # move the zone away: the tracker leaves it
    moved = [[lat + 0.01, lon] for lat, lon in SHOP]
    await client.send_json_auto_id(
        {"type": "shape_zones/save_zone", "zone_id": zone_id, "name": "Winkel", "points": moved}
    )
    msg = await client.receive_json()
    assert msg["success"]
    assert msg["result"]["icon"] == "mdi:vector-square"
    await settle(hass)
    assert hass.states.get(TRACKER).state == "not_home"
    assert entry.options[CONF_ZONES][0]["points"] == moved

    await client.send_json_auto_id({"type": "shape_zones/delete_zone", "zone_id": zone_id})
    assert (await client.receive_json())["success"]
    await settle(hass)
    assert hass.states.get(SENSOR) is None

    await client.send_json_auto_id({"type": "shape_zones/delete_zone", "zone_id": zone_id})
    assert (await client.receive_json())["error"]["code"] == "not_found"


async def test_requires_admin(hass: HomeAssistant, hass_ws_client, hass_read_only_access_token) -> None:
    await setup_entry(hass)
    client = await hass_ws_client(hass, hass_read_only_access_token)
    await client.send_json_auto_id({"type": "shape_zones/get"})
    msg = await client.receive_json()
    assert msg["error"]["code"] == "unauthorized"
