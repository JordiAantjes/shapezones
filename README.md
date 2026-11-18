# Shape Zones

Rectangular and polygon zones for Home Assistant. Built-in zones are always circles, which fit a shop, a house or a plot badly. Shape Zones lets you draw them as they are and shows them on your person card ("Winkel" instead of "Away"), and you can use them in automations.

No external Python packages: the point-in-polygon check is plain Python, so it runs on every Home Assistant installation.

## How it works

For every GPS tracker you choose (e.g. your phone from the Companion app), Shape Zones creates its own tracker, `device_tracker.shape_zones_<name>`:

- inside a shape zone, its state is the zone's name;
- outside, Home Assistant's normal zones apply (`home`, `not_home`, your round zones).

Link that tracker to your **person** instead of the original one, and the person shows the shape zone too.

You also get:

| Entity / event | What it does |
|---|---|
| `binary_sensor.shape_zones_<zone>` | On while one of the trackers is inside. Attributes: `count`, `names`, `trackers`, `points` |
| event `shape_zones_enter` / `shape_zones_leave` | Fired when a tracker enters/leaves a zone. Data: `entity_id`, `source`, `zone`, `zone_id` |

When zones overlap, the smallest one wins (a shop inside a business park).

## Installation

**HACS:** HACS → ⋮ → Custom repositories → add this repository's URL, category *Integration* → install **Shape Zones** → restart Home Assistant.

**Manual:** copy `custom_components/shape_zones` to `config/custom_components/` and restart.

Then: Settings → Devices & services → Add integration → **Shape Zones**, and pick the trackers to follow.

## Adding zones

### On the map (recommended)

Open **Shape Zones** in the sidebar (admins only).

- **New zone** puts a rectangle in the middle of the map. Drag its corners into place and drag ✥ to move it.
- Untick **Keep it a rectangle** for any other shape: drag the small dots between corners to add a corner, and right-click (or double-click) a corner to remove it.
- Click a zone on the map or in the list to edit or delete it.
- Switch between map and aerial photo at the top right. The map is Esri's street map (dark grey in a dark theme); in the Netherlands PDOK's BRT map is the default and PDOK's high-resolution aerial photo is available too. The choice is remembered per browser. Your trackers are shown as pink dots, Home Assistant's own zones as dashed circles.

### By coordinates

Settings → Devices & services → Shape Zones → **Configure** → *Add zone*.

Coordinates, one `lat, lon` per line:

- **2 points** = a rectangle with those two opposite corners. In Google Maps, right-click a corner and click the coordinates to copy them.
- **3 or more points** = a polygon through the points, in order.
- Or paste **GeoJSON** (e.g. drawn on [geojson.io](https://geojson.io)); the first polygon is used.

```
53.21917, 6.56502
53.21985, 6.56671
```

Then go to Settings → People → your person, and replace the phone's tracker with `device_tracker.shape_zones_<phone>`.

## Settings

| Setting | Default | Meaning |
|---|---|---|
| Maximum GPS inaccuracy | 100 m | Position fixes less accurate than this don't move a tracker in or out of a shape zone. |
| Edge margin | 10 m | You leave a zone only once you are this far outside it, so GPS jitter at the edge doesn't flip the state. |

## Automation examples

```yaml
# Person-based (state of the person or the tracker)
triggers:
  - trigger: state
    entity_id: person.jordi
    to: "Winkel"

# Anyone in the zone
triggers:
  - trigger: state
    entity_id: binary_sensor.shape_zones_winkel
    to: "on"

# Event with details
triggers:
  - trigger: event
    event_type: shape_zones_leave
    event_data:
      zone: Winkel
```

## Limitations

- The built-in `zone` trigger and `zone.*` counters don't know shape zones; use the triggers above.
- The default map card doesn't draw the shapes (the corners are in the sensor's `points` attribute); use the Shape Zones page to see them.

## Credits

The map uses [Leaflet](https://leafletjs.com) (BSD 2-Clause, included in `frontend/leaflet/`), with tiles from Esri and PDOK (no API keys needed).

## Development

```bash
python3.13 -m venv venv && ./venv/bin/pip install pytest-homeassistant-custom-component
./venv/bin/pytest
```
