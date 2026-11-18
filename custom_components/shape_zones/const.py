"""Constants for Shape Zones."""

DOMAIN = "shape_zones"

CONF_ZONES = "zones"
CONF_TRACKERS = "trackers"
CONF_COORDINATES = "coordinates"
CONF_POINTS = "points"
CONF_MAX_ACCURACY = "max_accuracy"
CONF_MARGIN = "margin"
CONF_ZONE_ID = "zone_id"

DEFAULT_MAX_ACCURACY = 100  # metres; fixes less accurate than this don't change the zone
DEFAULT_MARGIN = 10  # metres; you leave a zone only once you are this far outside it
DEFAULT_ICON = "mdi:vector-square"

EVENT_ENTER = "shape_zones_enter"
EVENT_LEAVE = "shape_zones_leave"

ATTR_SOURCE = "source"
ATTR_SHAPE_ZONE = "shape_zone"
ATTR_SHAPE_ZONE_ID = "shape_zone_id"

SIGNAL_OCCUPANCY = f"{DOMAIN}_occupancy_{{}}"
