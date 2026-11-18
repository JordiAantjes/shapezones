"""Dependency-free geometry for Shape Zones.

Zones are small (a building, a plot), so coordinates are projected onto a flat
plane in metres around the zone's own centre. The error that introduces is far
below GPS accuracy at that scale.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
import json
import math
import re
from typing import Any

M_PER_DEG_LAT = 110_574.0
M_PER_DEG_LON_AT_EQUATOR = 111_320.0

LatLon = tuple[float, float]

_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


class InvalidShape(ValueError):
    """Coordinates could not be turned into a zone.

    ``key`` is the translation key of the error shown in the UI.
    """

    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key


def parse_coordinates(text: str) -> list[LatLon]:
    """Turn user input into the corner points of a zone.

    Accepted input:
    * two points ("lat, lon" each)  -> the rectangle with those opposite corners
    * three or more points          -> a polygon through those points, in order
    * a GeoJSON Polygon, Feature or FeatureCollection (e.g. from geojson.io)
    """
    text = (text or "").strip()
    if not text:
        raise InvalidShape("empty")

    if text.startswith("{"):
        points = _points_from_geojson(text)
    else:
        numbers = [float(n) for n in _NUMBER.findall(text)]
        if len(numbers) % 2:
            raise InvalidShape("uneven_numbers")
        points = list(zip(numbers[0::2], numbers[1::2], strict=True))

    for lat, lon in points:
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise InvalidShape("out_of_range")

    if len(points) == 2:
        (lat1, lon1), (lat2, lon2) = points
        if lat1 == lat2 or lon1 == lon2:
            raise InvalidShape("too_few_points")
        points = [(lat1, lon1), (lat1, lon2), (lat2, lon2), (lat2, lon1)]

    points = _clean(points)
    if len(points) < 3:
        raise InvalidShape("too_few_points")
    return points


def _points_from_geojson(text: str) -> list[LatLon]:
    try:
        data = json.loads(text)
    except ValueError as err:
        raise InvalidShape("invalid_geojson") from err

    geometry = _first_polygon(data)
    if geometry is None:
        raise InvalidShape("invalid_geojson")
    try:
        ring = geometry["coordinates"][0]
        # GeoJSON stores [longitude, latitude]
        return [(float(p[1]), float(p[0])) for p in ring]
    except (KeyError, IndexError, TypeError, ValueError) as err:
        raise InvalidShape("invalid_geojson") from err


def _first_polygon(data: Any) -> dict | None:
    if not isinstance(data, dict):
        return None
    kind = data.get("type")
    if kind == "Polygon":
        return data
    if kind == "MultiPolygon":
        coords = data.get("coordinates") or []
        return {"type": "Polygon", "coordinates": coords[0]} if coords else None
    if kind == "Feature":
        return _first_polygon(data.get("geometry"))
    if kind == "FeatureCollection":
        for feature in data.get("features") or []:
            if (found := _first_polygon(feature)) is not None:
                return found
    return None


def _clean(points: Iterable[LatLon]) -> list[LatLon]:
    """Drop repeated consecutive points and a closing point equal to the first."""
    out: list[LatLon] = []
    for point in points:
        if not out or out[-1] != point:
            out.append(point)
    while len(out) > 1 and out[0] == out[-1]:
        out.pop()
    return out


class ShapeZone:
    """A named polygon on the map."""

    def __init__(
        self,
        zone_id: str,
        name: str,
        points: Sequence[Sequence[float]],
        icon: str | None = None,
    ) -> None:
        if len(points) < 3:
            raise InvalidShape("too_few_points")
        self.zone_id = zone_id
        self.name = name
        self.icon = icon
        self.points: list[LatLon] = [(float(p[0]), float(p[1])) for p in points]

        self._lat0 = sum(p[0] for p in self.points) / len(self.points)
        self._lon0 = sum(p[1] for p in self.points) / len(self.points)
        self._kx = M_PER_DEG_LON_AT_EQUATOR * math.cos(math.radians(self._lat0))
        self._xy = [self._project(lat, lon) for lat, lon in self.points]
        self.area = abs(
            sum(
                x1 * y2 - x2 * y1
                for (x1, y1), (x2, y2) in self._edges()
            )
        ) / 2

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ShapeZone:
        """Build a zone from its stored form."""
        return cls(data["id"], data["name"], data["points"], data.get("icon"))

    def _edges(self):
        return zip(self._xy, self._xy[1:] + self._xy[:1], strict=True)

    def _project(self, lat: float, lon: float) -> tuple[float, float]:
        return ((lon - self._lon0) * self._kx, (lat - self._lat0) * M_PER_DEG_LAT)

    def contains(self, lat: float, lon: float) -> bool:
        """Return True if the point lies inside the zone (even-odd rule)."""
        x, y = self._project(lat, lon)
        inside = False
        for (x1, y1), (x2, y2) in self._edges():
            if (y1 > y) != (y2 > y):
                x_cross = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
                if x < x_cross:
                    inside = not inside
        return inside

    def distance_outside(self, lat: float, lon: float) -> float:
        """Distance in metres from the point to the zone; 0 when inside."""
        if self.contains(lat, lon):
            return 0.0
        px, py = self._project(lat, lon)
        return min(
            _segment_distance(px, py, x1, y1, x2, y2)
            for (x1, y1), (x2, y2) in self._edges()
        )


def _segment_distance(
    px: float, py: float, x1: float, y1: float, x2: float, y2: float
) -> float:
    dx, dy = x2 - x1, y2 - y1
    length_sq = dx * dx + dy * dy
    t = 0.0 if length_sq == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / length_sq))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def resolve_zone(
    zones: Iterable[ShapeZone],
    lat: float,
    lon: float,
    current_id: str | None,
    margin: float,
) -> ShapeZone | None:
    """Pick the zone a position belongs to.

    The current zone is kept until the position is more than ``margin`` metres
    outside it, so GPS jitter at the edge doesn't flip the state. When zones
    overlap, the smallest one wins (a shop inside a business park, say).
    """
    candidates = [
        zone
        for zone in zones
        if zone.contains(lat, lon)
        or (zone.zone_id == current_id and zone.distance_outside(lat, lon) <= margin)
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda zone: (zone.area, zone.zone_id != current_id))
