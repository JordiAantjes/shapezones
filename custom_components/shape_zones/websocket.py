"""Websocket API used by the Shape Zones map panel."""

from __future__ import annotations

import copy
from typing import Any
import uuid

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ICON, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .const import CONF_POINTS, CONF_ZONES, DEFAULT_ICON, DOMAIN
from .geometry import InvalidShape, ShapeZone

POINT = vol.All(
    vol.ExactSequence([vol.Coerce(float), vol.Coerce(float)]),
    vol.Length(min=2, max=2),
)


@callback
def async_register(hass: HomeAssistant) -> None:
    """Register the commands (once per Home Assistant run)."""
    websocket_api.async_register_command(hass, ws_get)
    websocket_api.async_register_command(hass, ws_save_zone)
    websocket_api.async_register_command(hass, ws_delete_zone)


def _entry(hass: HomeAssistant) -> ConfigEntry | None:
    entries = hass.config_entries.async_entries(DOMAIN)
    return entries[0] if entries else None


def _payload(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    registry = er.async_get(hass)
    trackers = [
        e.entity_id
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == "device_tracker"
    ]
    return {"zones": list(entry.options.get(CONF_ZONES, [])), "trackers": trackers}


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/get"})
@websocket_api.require_admin
@callback
def ws_get(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    """Return all zones and our tracker entity ids."""
    if (entry := _entry(hass)) is None:
        connection.send_error(msg["id"], "not_set_up", "Shape Zones is not set up")
        return
    connection.send_result(msg["id"], _payload(hass, entry))


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/save_zone",
        vol.Optional("zone_id"): str,
        vol.Required(CONF_NAME): vol.All(str, vol.Strip, vol.Length(min=1)),
        vol.Optional(CONF_ICON): vol.Any(None, str),
        vol.Required(CONF_POINTS): vol.All([POINT], vol.Length(min=3)),
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_save_zone(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Create a zone, or replace the zone with the given id."""
    if (entry := _entry(hass)) is None:
        connection.send_error(msg["id"], "not_set_up", "Shape Zones is not set up")
        return

    zone_id = msg.get("zone_id")
    options = copy.deepcopy(dict(entry.options))
    zones: list[dict[str, Any]] = options.setdefault(CONF_ZONES, [])
    existing = next((z for z in zones if z["id"] == zone_id), None)
    if zone_id is not None and existing is None:
        connection.send_error(msg["id"], "not_found", "Zone not found")
        return

    name = msg[CONF_NAME]
    if any(z["name"].casefold() == name.casefold() and z["id"] != zone_id for z in zones):
        connection.send_error(msg["id"], "name_exists", "A zone with this name already exists")
        return

    points = [[lat, lon] for lat, lon in msg[CONF_POINTS]]
    if any(not (-90 <= lat <= 90 and -180 <= lon <= 180) for lat, lon in points):
        connection.send_error(msg["id"], "out_of_range", "Coordinates out of range")
        return

    zone = {
        "id": zone_id or uuid.uuid4().hex,
        CONF_NAME: name,
        CONF_ICON: msg.get(CONF_ICON) or (existing or {}).get(CONF_ICON) or DEFAULT_ICON,
        CONF_POINTS: points,
    }
    try:
        ShapeZone.from_dict(zone)
    except InvalidShape as err:
        connection.send_error(msg["id"], err.key, "Invalid shape")
        return

    if existing is None:
        zones.append(zone)
    else:
        zones[zones.index(existing)] = zone
    hass.config_entries.async_update_entry(entry, options=options)
    connection.send_result(msg["id"], zone)


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/delete_zone", vol.Required("zone_id"): str}
)
@websocket_api.require_admin
@callback
def ws_delete_zone(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Delete a zone."""
    if (entry := _entry(hass)) is None:
        connection.send_error(msg["id"], "not_set_up", "Shape Zones is not set up")
        return
    options = copy.deepcopy(dict(entry.options))
    zones = options.get(CONF_ZONES, [])
    remaining = [z for z in zones if z["id"] != msg["zone_id"]]
    if len(remaining) == len(zones):
        connection.send_error(msg["id"], "not_found", "Zone not found")
        return
    options[CONF_ZONES] = remaining
    hass.config_entries.async_update_entry(entry, options=options)
    connection.send_result(msg["id"])
