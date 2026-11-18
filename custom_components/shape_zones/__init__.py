"""Shape Zones: rectangular and polygon zones for Home Assistant."""

from __future__ import annotations

from dataclasses import dataclass, field

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

from .const import (
    CONF_MARGIN,
    CONF_MAX_ACCURACY,
    CONF_TRACKERS,
    CONF_ZONES,
    DEFAULT_MARGIN,
    DEFAULT_MAX_ACCURACY,
    DOMAIN,
)
from .geometry import ShapeZone

PLATFORMS = [Platform.BINARY_SENSOR, Platform.DEVICE_TRACKER]


@dataclass
class ShapeZonesData:
    """Runtime state shared by the entities of one config entry."""

    zones: list[ShapeZone]
    trackers: list[str]
    max_accuracy: float
    margin: float
    device_info: DeviceInfo
    # our tracker entity_id -> id of the shape zone it is in (or None)
    occupancy: dict[str, str | None] = field(default_factory=dict)
    # our tracker entity_id -> display name
    tracker_names: dict[str, str] = field(default_factory=dict)


type ShapeZonesConfigEntry = ConfigEntry[ShapeZonesData]


def tracker_unique_id(entry_id: str, source: str) -> str:
    """Unique id of the tracker that follows ``source``."""
    return f"{entry_id}_tracker_{source}"


def zone_unique_id(entry_id: str, zone_id: str) -> str:
    """Unique id of the occupancy sensor of a zone."""
    return f"{entry_id}_zone_{zone_id}"


async def async_setup_entry(hass: HomeAssistant, entry: ShapeZonesConfigEntry) -> bool:
    """Set up Shape Zones from a config entry."""
    options = entry.options
    zones = [ShapeZone.from_dict(z) for z in options.get(CONF_ZONES, [])]
    trackers = list(options.get(CONF_TRACKERS, []))

    entry.runtime_data = ShapeZonesData(
        zones=zones,
        trackers=trackers,
        max_accuracy=float(options.get(CONF_MAX_ACCURACY, DEFAULT_MAX_ACCURACY)),
        margin=float(options.get(CONF_MARGIN, DEFAULT_MARGIN)),
        device_info=DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Shape Zones",
            entry_type=DeviceEntryType.SERVICE,
        ),
    )

    _remove_orphans(hass, entry, zones, trackers)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ShapeZonesConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: ShapeZonesConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _remove_orphans(
    hass: HomeAssistant,
    entry: ConfigEntry,
    zones: list[ShapeZone],
    trackers: list[str],
) -> None:
    """Remove entities of zones and trackers that were deleted in the options."""
    wanted = {zone_unique_id(entry.entry_id, z.zone_id) for z in zones} | {
        tracker_unique_id(entry.entry_id, t) for t in trackers
    }
    registry = er.async_get(hass)
    for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if reg_entry.unique_id not in wanted:
            registry.async_remove(reg_entry.entity_id)
