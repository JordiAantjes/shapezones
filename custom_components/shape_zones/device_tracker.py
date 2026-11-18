"""Trackers that report the shape zone a device is in.

Each tracker follows one existing GPS tracker (e.g. the Companion app). Inside
a shape zone its state is that zone's name; outside, Home Assistant's normal
round zones apply (home, not_home, ...). Link it to a person instead of the
original tracker and the person shows the shape zone too.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.const import (
    ATTR_FRIENDLY_NAME,
    ATTR_GPS_ACCURACY,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity

from . import ShapeZonesConfigEntry, ShapeZonesData, tracker_unique_id
from .const import (
    ATTR_SHAPE_ZONE,
    ATTR_SHAPE_ZONE_ID,
    ATTR_SOURCE,
    EVENT_ENTER,
    EVENT_LEAVE,
    SIGNAL_OCCUPANCY,
)
from .geometry import ShapeZone, resolve_zone


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ShapeZonesConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create one tracker per followed source tracker."""
    data = entry.runtime_data
    entities = []
    for source in data.trackers:
        state = hass.states.get(source)
        name = (
            state.attributes.get(ATTR_FRIENDLY_NAME)
            if state is not None
            else None
        ) or source.split(".", 1)[1].replace("_", " ")
        entities.append(ShapeZoneTracker(entry.entry_id, data, source, name))
    async_add_entities(entities)


class ShapeZoneTracker(TrackerEntity, RestoreEntity):
    """GPS tracker whose location name is the shape zone it is in."""

    _attr_has_entity_name = True
    _attr_entity_category = None
    _attr_source_type = SourceType.GPS
    _attr_icon = "mdi:map-marker-radius"
    _attr_should_poll = False

    def __init__(
        self, entry_id: str, data: ShapeZonesData, source: str, name: str
    ) -> None:
        self._entry_id = entry_id
        self._data = data
        self._source = source
        self._zone: ShapeZone | None = None
        self._initialised = False

        self._attr_name = name
        self._attr_unique_id = tracker_unique_id(entry_id, source)
        self._attr_device_info = data.device_info

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Show which tracker is followed and which shape zone matched."""
        return {
            ATTR_SOURCE: self._source,
            ATTR_SHAPE_ZONE: self._zone.name if self._zone else None,
            ATTR_SHAPE_ZONE_ID: self._zone.zone_id if self._zone else None,
        }

    async def async_added_to_hass(self) -> None:
        """Restore the last position, then follow the source tracker."""
        await super().async_added_to_hass()
        self._data.tracker_names[self.entity_id] = self._attr_name or self.entity_id

        if (last := await self.async_get_last_state()) is not None:
            attrs = last.attributes
            if attrs.get(ATTR_LATITUDE) is not None and attrs.get(ATTR_LONGITUDE) is not None:
                self._attr_latitude = float(attrs[ATTR_LATITUDE])
                self._attr_longitude = float(attrs[ATTR_LONGITUDE])
                self._attr_location_accuracy = float(attrs.get(ATTR_GPS_ACCURACY) or 0)
            zone_id = attrs.get(ATTR_SHAPE_ZONE_ID)
            self._zone = next(
                (z for z in self._data.zones if z.zone_id == zone_id), None
            )
            self._attr_location_name = self._zone.name if self._zone else None
            self._publish_occupancy()

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._source], self._async_source_changed
            )
        )
        self._update_from_source(fire_events=False)
        self._initialised = True

    async def async_will_remove_from_hass(self) -> None:
        """Forget this tracker in the occupancy overview."""
        self._data.occupancy.pop(self.entity_id, None)
        self._data.tracker_names.pop(self.entity_id, None)
        async_dispatcher_send(self.hass, SIGNAL_OCCUPANCY.format(self._entry_id))

    @callback
    def _async_source_changed(self, event: Event[EventStateChangedData]) -> None:
        self._update_from_source(fire_events=True)

    @callback
    def _update_from_source(self, fire_events: bool) -> None:
        state = self.hass.states.get(self._source)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return  # keep the last known position

        lat = state.attributes.get(ATTR_LATITUDE)
        lon = state.attributes.get(ATTR_LONGITUDE)

        if lat is None or lon is None:
            # A tracker without coordinates (router, Bluetooth): pass its state on.
            self._attr_latitude = self._attr_longitude = None
            self._attr_location_name = state.state
            self._set_zone(None, fire_events)
            self.async_write_ha_state()
            return

        accuracy = float(state.attributes.get(ATTR_GPS_ACCURACY) or 0)
        self._attr_latitude = float(lat)
        self._attr_longitude = float(lon)
        self._attr_location_accuracy = accuracy

        if accuracy <= self._data.max_accuracy or not self._initialised:
            zone = resolve_zone(
                self._data.zones,
                self._attr_latitude,
                self._attr_longitude,
                self._zone.zone_id if self._zone else None,
                self._data.margin,
            )
            self._set_zone(zone, fire_events)
        # else: too inaccurate to move between shape zones; keep the current one

        # None lets Home Assistant fall back to its own (round) zones
        self._attr_location_name = self._zone.name if self._zone else None
        self.async_write_ha_state()

    @callback
    def _set_zone(self, zone: ShapeZone | None, fire_events: bool) -> None:
        old = self._zone
        if (old.zone_id if old else None) == (zone.zone_id if zone else None):
            return
        self._zone = zone
        self._publish_occupancy()

        if not fire_events:
            return
        base = {"entity_id": self.entity_id, ATTR_SOURCE: self._source}
        if old is not None:
            self.hass.bus.async_fire(
                EVENT_LEAVE, {**base, "zone": old.name, "zone_id": old.zone_id}
            )
        if zone is not None:
            self.hass.bus.async_fire(
                EVENT_ENTER, {**base, "zone": zone.name, "zone_id": zone.zone_id}
            )

    @callback
    def _publish_occupancy(self) -> None:
        self._data.occupancy[self.entity_id] = self._zone.zone_id if self._zone else None
        async_dispatcher_send(self.hass, SIGNAL_OCCUPANCY.format(self._entry_id))
