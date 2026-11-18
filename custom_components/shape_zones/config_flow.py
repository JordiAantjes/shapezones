"""Config and options flow for Shape Zones."""

from __future__ import annotations

import copy
from typing import Any
import uuid

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_ICON, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    IconSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
)

from .const import (
    CONF_COORDINATES,
    CONF_MARGIN,
    CONF_MAX_ACCURACY,
    CONF_POINTS,
    CONF_TRACKERS,
    CONF_ZONE_ID,
    CONF_ZONES,
    DEFAULT_ICON,
    DEFAULT_MARGIN,
    DEFAULT_MAX_ACCURACY,
    DOMAIN,
)
from .geometry import InvalidShape, parse_coordinates

ZONE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): TextSelector(),
        vol.Required(CONF_COORDINATES): TextSelector(TextSelectorConfig(multiline=True)),
        vol.Optional(CONF_ICON): IconSelector(),
    }
)

TRACKERS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_TRACKERS, default=[]): EntitySelector(
            EntitySelectorConfig(domain="device_tracker", multiple=True)
        )
    }
)

SETTINGS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_MAX_ACCURACY): NumberSelector(
            NumberSelectorConfig(
                min=5, max=2000, step=5, unit_of_measurement="m", mode=NumberSelectorMode.BOX
            )
        ),
        vol.Required(CONF_MARGIN): NumberSelector(
            NumberSelectorConfig(
                min=0, max=500, step=1, unit_of_measurement="m", mode=NumberSelectorMode.BOX
            )
        ),
    }
)


def _tracker_errors(hass: HomeAssistant, trackers: list[str]) -> dict[str, str]:
    """Our own trackers can't follow each other."""
    registry = er.async_get(hass)
    for entity_id in trackers:
        reg_entry = registry.async_get(entity_id)
        if reg_entry is not None and reg_entry.platform == DOMAIN:
            return {CONF_TRACKERS: "own_tracker"}
    return {}


def _points_to_text(points: list[list[float]]) -> str:
    return "\n".join(f"{lat}, {lon}" for lat, lon in points)


class ShapeZonesConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up Shape Zones (one instance holds all zones)."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the trackers to follow; zones are added afterwards."""
        errors: dict[str, str] = {}
        if user_input is not None:
            trackers = user_input.get(CONF_TRACKERS, [])
            errors = _tracker_errors(self.hass, trackers)
            if not errors:
                return self.async_create_entry(
                    title="Shape Zones",
                    data={},
                    options={
                        CONF_ZONES: [],
                        CONF_TRACKERS: trackers,
                        CONF_MAX_ACCURACY: DEFAULT_MAX_ACCURACY,
                        CONF_MARGIN: DEFAULT_MARGIN,
                    },
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(TRACKERS_SCHEMA, user_input or {}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Manage zones, trackers and settings."""
        return ShapeZonesOptionsFlow()


class ShapeZonesOptionsFlow(OptionsFlow):
    """Menu to add, edit and remove zones and to change trackers and settings."""

    def __init__(self) -> None:
        self._edit_id: str | None = None

    def _options(self) -> dict[str, Any]:
        return copy.deepcopy(dict(self.config_entry.options))

    def _zones(self) -> list[dict[str, Any]]:
        return list(self.config_entry.options.get(CONF_ZONES, []))

    def _zone_options(self) -> list[SelectOptionDict]:
        return [SelectOptionDict(value=z["id"], label=z["name"]) for z in self._zones()]

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Main menu."""
        menu = ["add_zone"]
        if self._zones():
            menu += ["pick_zone", "remove_zones"]
        menu += ["trackers", "settings"]
        return self.async_show_menu(step_id="init", menu_options=menu)

    async def async_step_add_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a zone."""
        return await self._zone_form("add_zone", None, user_input)

    async def async_step_pick_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the zone to edit."""
        if user_input is not None:
            self._edit_id = user_input[CONF_ZONE_ID]
            return await self.async_step_edit_zone()
        return self.async_show_form(
            step_id="pick_zone",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ZONE_ID): SelectSelector(
                        SelectSelectorConfig(options=self._zone_options())
                    )
                }
            ),
        )

    async def async_step_edit_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the chosen zone."""
        return await self._zone_form("edit_zone", self._edit_id, user_input)

    async def _zone_form(
        self, step_id: str, zone_id: str | None, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        options = self._options()
        zones: list[dict[str, Any]] = options.setdefault(CONF_ZONES, [])
        current = next((z for z in zones if z["id"] == zone_id), None)
        errors: dict[str, str] = {}

        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            if not name:
                errors[CONF_NAME] = "name_empty"
            elif any(
                z["name"].casefold() == name.casefold() and z["id"] != zone_id
                for z in zones
            ):
                errors[CONF_NAME] = "name_exists"
            try:
                points = parse_coordinates(user_input[CONF_COORDINATES])
            except InvalidShape as err:
                errors[CONF_COORDINATES] = err.key

            if not errors:
                zone = {
                    "id": zone_id or uuid.uuid4().hex,
                    CONF_NAME: name,
                    CONF_ICON: user_input.get(CONF_ICON) or DEFAULT_ICON,
                    CONF_POINTS: [list(p) for p in points],
                }
                if current is None:
                    zones.append(zone)
                else:
                    zones[zones.index(current)] = zone
                return self.async_create_entry(data=options)
            suggested = user_input
        elif current is not None:
            suggested = {
                CONF_NAME: current[CONF_NAME],
                CONF_COORDINATES: _points_to_text(current[CONF_POINTS]),
                CONF_ICON: current.get(CONF_ICON),
            }
        else:
            suggested = {}

        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(ZONE_SCHEMA, suggested),
            errors=errors,
        )

    async def async_step_remove_zones(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Remove one or more zones."""
        if user_input is not None:
            remove = set(user_input.get(CONF_ZONES, []))
            options = self._options()
            options[CONF_ZONES] = [z for z in options[CONF_ZONES] if z["id"] not in remove]
            return self.async_create_entry(data=options)
        return self.async_show_form(
            step_id="remove_zones",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_ZONES, default=[]): SelectSelector(
                        SelectSelectorConfig(options=self._zone_options(), multiple=True)
                    )
                }
            ),
        )

    async def async_step_trackers(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose which trackers to follow."""
        errors: dict[str, str] = {}
        if user_input is not None:
            trackers = user_input.get(CONF_TRACKERS, [])
            errors = _tracker_errors(self.hass, trackers)
            if not errors:
                options = self._options()
                options[CONF_TRACKERS] = trackers
                return self.async_create_entry(data=options)
        return self.async_show_form(
            step_id="trackers",
            data_schema=self.add_suggested_values_to_schema(
                TRACKERS_SCHEMA,
                user_input or {CONF_TRACKERS: self.config_entry.options.get(CONF_TRACKERS, [])},
            ),
            errors=errors,
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """GPS accuracy and edge margin."""
        if user_input is not None:
            options = self._options()
            options[CONF_MAX_ACCURACY] = user_input[CONF_MAX_ACCURACY]
            options[CONF_MARGIN] = user_input[CONF_MARGIN]
            return self.async_create_entry(data=options)
        current = self.config_entry.options
        return self.async_show_form(
            step_id="settings",
            data_schema=self.add_suggested_values_to_schema(
                SETTINGS_SCHEMA,
                {
                    CONF_MAX_ACCURACY: current.get(CONF_MAX_ACCURACY, DEFAULT_MAX_ACCURACY),
                    CONF_MARGIN: current.get(CONF_MARGIN, DEFAULT_MARGIN),
                },
            ),
        )
