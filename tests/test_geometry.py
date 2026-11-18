"""Geometry tests (no Home Assistant needed)."""

import json

import pytest

from custom_components.shape_zones.geometry import (
    InvalidShape,
    ShapeZone,
    parse_coordinates,
    resolve_zone,
)

# roughly 110 m (north-south) by 135 m (east-west) near Groningen
RECT = "53.2190, 6.5650\n53.2200, 6.5670"


def test_two_points_make_a_rectangle():
    points = parse_coordinates(RECT)
    assert points == [(53.219, 6.565), (53.219, 6.567), (53.22, 6.567), (53.22, 6.565)]


def test_google_maps_copy_paste_on_one_line():
    assert len(parse_coordinates("53.2190, 6.5650 53.2200, 6.5670")) == 4


def test_geojson_is_lon_lat():
    geo = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[6.565, 53.219], [6.567, 53.219], [6.567, 53.22], [6.565, 53.219]]],
                },
            }
        ],
    }
    assert parse_coordinates(json.dumps(geo)) == [(53.219, 6.565), (53.219, 6.567), (53.22, 6.567)]


@pytest.mark.parametrize(
    ("text", "key"),
    [
        ("", "empty"),
        ("53.2, 6.5, 53.3", "uneven_numbers"),
        ("153.2, 6.5\n53.3, 6.6", "out_of_range"),
        ("53.2, 6.5\n53.2, 6.6", "too_few_points"),
        ('{"type": "Point", "coordinates": [6.5, 53.2]}', "invalid_geojson"),
        ("{not json", "invalid_geojson"),
    ],
)
def test_invalid_input(text, key):
    with pytest.raises(InvalidShape) as err:
        parse_coordinates(text)
    assert err.value.key == key


def test_contains_and_distance():
    zone = ShapeZone("a", "Winkel", parse_coordinates(RECT))
    assert zone.contains(53.2195, 6.5660)
    assert not zone.contains(53.2205, 6.5660)
    # ~55 m north of the northern edge (0.0005 deg latitude)
    assert zone.distance_outside(53.2205, 6.5660) == pytest.approx(55.3, abs=1)
    assert 13_000 < zone.area < 16_000


def test_l_shaped_polygon():
    # L-shape: the inner corner is outside
    zone = ShapeZone(
        "l", "L",
        [(0, 0), (0, 0.002), (0.001, 0.002), (0.001, 0.001), (0.002, 0.001), (0.002, 0)],
    )
    assert zone.contains(0.0005, 0.0015)
    assert zone.contains(0.0015, 0.0005)
    assert not zone.contains(0.0015, 0.0015)


def test_hysteresis_keeps_current_zone_near_edge():
    zone = ShapeZone("a", "Winkel", parse_coordinates(RECT))
    just_outside = (53.22005, 6.5660)  # ~5.5 m outside
    assert resolve_zone([zone], *just_outside, current_id=None, margin=10) is None
    assert resolve_zone([zone], *just_outside, current_id="a", margin=10) is zone
    assert resolve_zone([zone], 53.2205, 6.5660, current_id="a", margin=10) is None


def test_smallest_overlapping_zone_wins():
    big = ShapeZone("big", "Bedrijventerrein", parse_coordinates("53.218, 6.563\n53.221, 6.569"))
    small = ShapeZone("small", "Winkel", parse_coordinates(RECT))
    assert resolve_zone([big, small], 53.2195, 6.5660, None, 10) is small
    assert resolve_zone([big, small], 53.2185, 6.5640, None, 10) is big
