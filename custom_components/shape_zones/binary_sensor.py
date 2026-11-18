"""Occupancy sensor per shape zone: on while one of the trackers is inside."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ShapeZonesConfigEntry, ShapeZonesData, zone_unique_id
from .const import DEFAULT_ICON, SIGNAL_OCCUPANCY
from .geometry import ShapeZone


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ShapeZonesConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create one occupancy sensor per zone."""
    data = entry.runtime_data
    async_add_entities(
        ShapeZoneOccupancy(entry.entry_id, data, zone) for zone in data.zones
    )


class ShapeZoneOccupancy(BinarySensorEntity):
    """Whether anyone followed by Shape Zones is inside the zone."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY
    _attr_should_poll = False

    def __init__(self, entry_id: str, data: ShapeZonesData, zone: ShapeZone) -> None:
        self._entry_id = entry_id
        self._data = data
        self._zone = zone
        self._attr_name = zone.name
        self._attr_icon = zone.icon or DEFAULT_ICON
        self._attr_unique_id = zone_unique_id(entry_id, zone.zone_id)
        self._attr_device_info = data.device_info
        self._members: list[str] = []

    @property
    def is_on(self) -> bool:
        """On while at least one tracker is in the zone."""
        return bool(self._members)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Who is in the zone, plus its corners (lat, lon)."""
        return {
            "count": len(self._members),
            "trackers": self._members,
            "names": [self._data.tracker_names.get(m, m) for m in self._members],
            "points": [list(p) for p in self._zone.points],
        }

    async def async_added_to_hass(self) -> None:
        """Follow occupancy changes of the trackers."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_OCCUPANCY.format(self._entry_id), self._refresh
            )
        )
        self._refresh(write=False)

    @callback
    def _refresh(self, write: bool = True) -> None:
        members = sorted(
            entity_id
            for entity_id, zone_id in self._data.occupancy.items()
            if zone_id == self._zone.zone_id
        )
        if members == self._members and write:
            return
        self._members = members
        if write:
            self.async_write_ha_state()
