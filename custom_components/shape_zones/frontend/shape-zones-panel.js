// Shape Zones map editor: a sidebar panel to draw and edit zones on a map.
import * as L from "./leaflet/leaflet-src.esm.js";

const STRINGS = {
  en: {
    title: "Shape Zones",
    new_zone: "New zone",
    zones: "Zones",
    no_zones: "No zones yet. Click “New zone” and drag the corners into place.",
    name: "Name",
    keep_rectangle: "Keep it a rectangle",
    hint_rect: "Drag a corner to resize. Drag ✥ to move the zone.",
    hint_free:
      "Drag a corner to move it. Drag a small dot between two corners to add a corner. Right-click (or double-click) a corner to remove it. Drag ✥ to move the zone.",
    save: "Save",
    cancel: "Cancel",
    delete: "Delete",
    confirm_delete: "Delete zone “{name}”?",
    confirm_discard: "Discard unsaved changes?",
    err_name: "Enter a name.",
    err_name_exists: "A zone with this name already exists.",
    err_generic: "Saving failed: {msg}",
    err_not_set_up: "Shape Zones is not set up yet. Add the integration first.",
    saved: "Saved",
    map: "Map",
    aerial: "Aerial photo",
    aerial_nl: "Aerial photo (NL, PDOK)",
    points: "{n} corners",
  },
  nl: {
    title: "Shape Zones",
    new_zone: "Nieuwe zone",
    zones: "Zones",
    no_zones: "Nog geen zones. Klik op “Nieuwe zone” en sleep de hoeken op hun plek.",
    name: "Naam",
    keep_rectangle: "Rechthoek houden",
    hint_rect: "Sleep een hoek om het formaat te wijzigen. Sleep ✥ om de zone te verplaatsen.",
    hint_free:
      "Sleep een hoek om hem te verplaatsen. Sleep een klein bolletje tussen twee hoeken om een hoek toe te voegen. Rechtsklik (of dubbelklik) op een hoek om hem te verwijderen. Sleep ✥ om de zone te verplaatsen.",
    save: "Opslaan",
    cancel: "Annuleren",
    delete: "Verwijderen",
    confirm_delete: "Zone “{name}” verwijderen?",
    confirm_discard: "Niet-opgeslagen wijzigingen weggooien?",
    err_name: "Vul een naam in.",
    err_name_exists: "Er bestaat al een zone met deze naam.",
    err_generic: "Opslaan mislukt: {msg}",
    err_not_set_up: "Shape Zones is nog niet ingesteld. Voeg eerst de integratie toe.",
    saved: "Opgeslagen",
    map: "Kaart",
    aerial: "Luchtfoto",
    aerial_nl: "Luchtfoto (NL, PDOK)",
    points: "{n} hoeken",
  },
};

const M_PER_DEG_LAT = 110574;

function areaM2(points) {
  if (points.length < 3) return 0;
  const lat0 = points.reduce((s, p) => s + p[0], 0) / points.length;
  const kx = 111320 * Math.cos((lat0 * Math.PI) / 180);
  const xy = points.map(([lat, lon]) => [lon * kx, lat * M_PER_DEG_LAT]);
  let sum = 0;
  for (let i = 0; i < xy.length; i++) {
    const [x1, y1] = xy[i];
    const [x2, y2] = xy[(i + 1) % xy.length];
    sum += x1 * y2 - x2 * y1;
  }
  return Math.abs(sum) / 2;
}

function isAxisRectangle(points) {
  if (points.length !== 4) return false;
  const [a, b, c, d] = points;
  const eq = (x, y) => Math.abs(x - y) < 1e-9;
  return (
    (eq(a[0], b[0]) && eq(b[1], c[1]) && eq(c[0], d[0]) && eq(d[1], a[1])) ||
    (eq(a[1], b[1]) && eq(b[0], c[0]) && eq(c[1], d[1]) && eq(d[0], a[0]))
  );
}

function rectangleFrom(lat1, lon1, lat2, lon2) {
  return [
    [lat1, lon1],
    [lat1, lon2],
    [lat2, lon2],
    [lat2, lon1],
  ];
}

function round(v) {
  return Math.round(v * 1e7) / 1e7;
}

const CSS = `
  :host([dark]) { --sz-control-icon-filter: invert(1); }
  :host { display: flex; flex-direction: column; height: 100vh; height: 100dvh; background: var(--primary-background-color); color: var(--primary-text-color); font-family: var(--ha-font-family-body, Roboto, sans-serif); }
  .toolbar { flex: none; display: flex; align-items: center; height: var(--header-height, 56px); padding: 0 12px; box-sizing: border-box;
    background: var(--app-header-background-color, var(--primary-color)); color: var(--app-header-text-color, white);
    border-bottom: var(--app-header-border-bottom, none); font-size: 20px; gap: 8px; }
  .body { flex: 1; min-height: 0; display: flex; }
  .side { width: 320px; flex: none; overflow-y: auto; padding: 16px; box-sizing: border-box;
    background: var(--card-background-color, white); border-right: 1px solid var(--divider-color, #ddd); }
  #map { flex: 1; min-width: 0; min-height: 0; }
  :host([narrow]) .body { flex-direction: column-reverse; }
  :host([narrow]) .side { width: 100%; max-height: 45%; border-right: none; border-top: 1px solid var(--divider-color, #ddd); }
  :host([narrow]) #map { min-height: 55%; }
  h2 { font-size: 14px; font-weight: 500; text-transform: uppercase; letter-spacing: .5px; color: var(--secondary-text-color); margin: 20px 0 8px; }
  button { font: inherit; font-size: 14px; font-weight: 500; border-radius: 18px; padding: 8px 16px; cursor: pointer;
    border: 1px solid var(--primary-color); background: transparent; color: var(--primary-color); }
  button.primary { background: var(--primary-color); color: var(--text-primary-color, white); }
  button.danger { border-color: var(--error-color, #db4437); color: var(--error-color, #db4437); }
  button:disabled { opacity: .5; cursor: default; }
  .zone { display: flex; justify-content: space-between; align-items: center; gap: 8px; padding: 10px 12px; border-radius: 8px; cursor: pointer; }
  .zone:hover { background: var(--secondary-background-color, #f5f5f5); }
  .zone.active { background: rgba(var(--rgb-primary-color, 3,169,244), .15); }
  .zone small { color: var(--secondary-text-color); white-space: nowrap; }
  .muted { color: var(--secondary-text-color); font-size: 14px; line-height: 1.5; }
  label { display: block; font-size: 14px; margin: 12px 0 4px; color: var(--secondary-text-color); }
  input[type=text] { width: 100%; box-sizing: border-box; font: inherit; padding: 10px 12px; border-radius: 6px;
    border: 1px solid var(--divider-color, #ccc); background: var(--secondary-background-color, #fafafa); color: var(--primary-text-color); }
  .check { display: flex; align-items: center; gap: 8px; margin: 12px 0; font-size: 14px; color: var(--primary-text-color); }
  .row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 16px; }
  .error { color: var(--error-color, #db4437); font-size: 14px; margin-top: 8px; }
  .ok { color: var(--success-color, #43a047); font-size: 14px; margin-top: 8px; }
  .handle { width: 14px; height: 14px; margin: -7px 0 0 -7px; border-radius: 50%; background: white; border: 3px solid #ff9800; box-sizing: border-box; cursor: grab; }
  .mid { width: 10px; height: 10px; margin: -5px 0 0 -5px; border-radius: 50%; background: #ff9800; opacity: .6; cursor: copy; }
  .move { width: 26px; height: 26px; margin: -13px 0 0 -13px; border-radius: 50%; background: #ff9800; color: white; font-size: 18px;
    line-height: 26px; text-align: center; cursor: move; box-shadow: 0 1px 4px rgba(0,0,0,.4); }
  .zone-label { background: rgba(0,0,0,.6); color: white; border: none; box-shadow: none; font-weight: 500; }
  .zone-label::before { display: none; }
  .leaflet-container { font: inherit; }
  .leaflet-bar a, .leaflet-control-layers, .leaflet-control-attribution, .leaflet-control-scale-line {
    background: var(--card-background-color, white); color: var(--primary-text-color, #333); border-color: var(--divider-color, #ccc); }
  .leaflet-bar a:hover { background: var(--secondary-background-color, #f4f4f4); }
  .leaflet-control-attribution a { color: var(--primary-color); }
  .leaflet-control-layers-toggle { filter: var(--sz-control-icon-filter, none); }
  .dark-tiles { filter: invert(1) hue-rotate(180deg) brightness(0.95) contrast(0.85); }
`;

class ShapeZonesPanel extends HTMLElement {
  constructor() {
    super();
    this._zones = [];
    this._trackers = [];
    this._edit = null; // {zone_id, name, points, rect, dirty}
    this._message = null;
  }

  set hass(hass) {
    this._hass = hass;
    if (this._menuButton) this._menuButton.hass = hass;
    if (this._map) this._drawTrackers();
    else this._maybeInit();
  }

  set narrow(narrow) {
    this._narrow = narrow;
    this.toggleAttribute("narrow", !!narrow);
    if (this._menuButton) this._menuButton.narrow = narrow;
    if (this._map) setTimeout(() => this._map && this._map.invalidateSize(), 50);
  }

  set panel(_panel) {}

  _t(key, vars = {}) {
    const lang = (this._hass?.language || "en").split("-")[0];
    let s = (STRINGS[lang] || STRINGS.en)[key] ?? STRINGS.en[key] ?? key;
    for (const [k, v] of Object.entries(vars)) s = s.replace(`{${k}}`, v);
    return s;
  }

  connectedCallback() {
    this._maybeInit();
  }

  disconnectedCallback() {
    this._teardown();
  }

  _maybeInit() {
    if (this._hass && this.isConnected && !this._initializing && !this._map) this._init();
  }

  async _init() {
    this._initializing = true;
    const root = this.shadowRoot || this.attachShadow({ mode: "open" });
    root.innerHTML = `
      <link rel="stylesheet" href="${new URL("./leaflet/leaflet.css", import.meta.url)}">
      <style>${CSS}</style>
      <div class="toolbar"><span id="menu"></span><span>${this._t("title")}</span></div>
      <div class="body"><div class="side" id="side"></div><div id="map"></div></div>`;

    this._menuButton = document.createElement("ha-menu-button");
    this._menuButton.hass = this._hass;
    this._menuButton.narrow = this._narrow;
    root.getElementById("menu").appendChild(this._menuButton);
    this._side = root.getElementById("side");
    this._edit = null;
    this._trackerSignature = null;
    this._renderSide();

    // Leaflet needs a visible container with a size; HA may hand us hass before we are shown
    const mapDiv = root.getElementById("map");
    const visible = await new Promise((resolve) => {
      const ro = new ResizeObserver(() => {
        if (!this.isConnected) {
          ro.disconnect();
          resolve(false);
        } else if (mapDiv.clientWidth > 0 && mapDiv.clientHeight > 0) {
          ro.disconnect();
          resolve(true);
        }
      });
      ro.observe(mapDiv);
      this._pendingObserver = ro;
    });
    this._pendingObserver = null;
    if (!visible || !this.isConnected) {
      this._initializing = false;
      return;
    }

    this._setupMap(mapDiv);
    this._resizeObserver = new ResizeObserver(() => this._map && this._map.invalidateSize());
    this._resizeObserver.observe(mapDiv);
    this._keyHandler = (ev) => {
      if (ev.key === "Escape" && this._edit) this._cancel();
    };
    window.addEventListener("keydown", this._keyHandler);
    this._initializing = false;

    await this._load(true);
  }

  _teardown() {
    if (this._pendingObserver) this._pendingObserver.disconnect();
    if (this._resizeObserver) this._resizeObserver.disconnect();
    if (this._keyHandler) window.removeEventListener("keydown", this._keyHandler);
    if (this._map) this._map.remove();
    this._pendingObserver = this._resizeObserver = this._keyHandler = this._map = null;
    this._initializing = false;
  }

  _setupMap(container) {
    const conf = this._hass.config;
    const map = L.map(container, { maxZoom: 21 });
    const dark = !!this._hass.themes?.darkMode;
    this.toggleAttribute("dark", dark);
    // No-key raster maps only: OpenStreetMap's own servers block requests without a
    // Referer (HA sends none) and CARTO now needs an API key.
    const esriTile = (service, maxNativeZoom) =>
      L.tileLayer(`https://server.arcgisonline.com/ArcGIS/rest/services/${service}/MapServer/tile/{z}/{y}/{x}`, {
        maxNativeZoom,
        maxZoom: 21,
        attribution: "Tiles &copy; Esri",
      });
    const streets = dark
      ? L.layerGroup([esriTile("Canvas/World_Dark_Gray_Base", 16), esriTile("Canvas/World_Dark_Gray_Reference", 16)])
      : esriTile("World_Street_Map", 19);
    const brt = L.tileLayer(
      "https://service.pdok.nl/brt/achtergrondkaart/wmts/v2_0/standaard/EPSG:3857/{z}/{x}/{y}.png",
      {
        minZoom: 6,
        maxNativeZoom: 19,
        maxZoom: 21,
        // PDOK has no dark map: invert it in a dark theme (hue-rotate keeps water blue)
        className: dark ? "dark-tiles" : "",
        attribution: '&copy; <a href="https://www.kadaster.nl">Kadaster</a> / PDOK',
      }
    );
    const esri = L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      { maxNativeZoom: 19, maxZoom: 21, attribution: "Tiles &copy; Esri" }
    );
    const pdok = L.tileLayer(
      "https://service.pdok.nl/hwh/luchtfotorgb/wmts/v1_0/Actueel_orthoHR/EPSG:3857/{z}/{x}/{y}.jpeg",
      { minZoom: 6, maxNativeZoom: 19, maxZoom: 21, attribution: '&copy; <a href="https://www.pdok.nl/">PDOK</a> Beeldmateriaal.nl' }
    );
    const nl = conf.country === "NL";
    // In the Netherlands the PDOK (Kadaster) map is the map; elsewhere Esri's street map.
    const layers = { [this._t("map")]: nl ? brt : streets };
    layers[this._t("aerial")] = esri;
    if (nl) layers[this._t("aerial_nl")] = pdok;

    // remember the chosen background per browser
    let saved = null;
    try {
      saved = localStorage.getItem("shape_zones_layer");
    } catch (_err) {
      // storage unavailable: fall back to the default
    }
    (layers[saved] || layers[this._t("map")]).addTo(map);
    map.on("baselayerchange", (ev) => {
      try {
        localStorage.setItem("shape_zones_layer", ev.name);
      } catch (_err) {
        // ignore
      }
    });
    L.control.layers(layers, null, { position: "topright" }).addTo(map);
    L.control.scale({ imperial: false }).addTo(map);

    map.setView([conf.latitude, conf.longitude], 17);
    this._map = map;
    this._contextLayer = L.layerGroup().addTo(map);
    this._zoneLayer = L.layerGroup().addTo(map);
    this._editLayer = L.layerGroup().addTo(map);
    this._trackerLayer = L.layerGroup().addTo(map);
    this._drawHaZones();
  }

  async _load(fit = false) {
    if (!this._map) return;
    try {
      const result = await this._hass.callWS({ type: "shape_zones/get" });
      this._zones = result.zones;
      this._trackers = result.trackers;
      this._error = null;
    } catch (err) {
      this._error = err.code === "not_set_up" ? this._t("err_not_set_up") : err.message;
    }
    if (!this._map) return; // page was closed while loading
    this._drawZones();
    this._drawTrackers();
    this._renderSide();
    if (fit && this._zones.length) {
      const bounds = L.latLngBounds(this._zones.flatMap((z) => z.points));
      this._map.fitBounds(bounds.pad(0.3), { maxZoom: 18 });
    }
  }

  // ---- drawing ----------------------------------------------------------

  _drawHaZones() {
    this._contextLayer.clearLayers();
    for (const state of Object.values(this._hass.states)) {
      if (!state.entity_id.startsWith("zone.")) continue;
      const { latitude, longitude, radius } = state.attributes;
      if (latitude == null || longitude == null) continue;
      L.circle([latitude, longitude], {
        radius: radius || 100,
        color: "#888",
        weight: 1,
        dashArray: "4 4",
        fillOpacity: 0.05,
        interactive: false,
      }).addTo(this._contextLayer);
    }
  }

  _drawZones() {
    this._zoneLayer.clearLayers();
    const primary = getComputedStyle(this).getPropertyValue("--primary-color").trim() || "#03a9f4";
    for (const zone of this._zones) {
      if (this._edit && this._edit.zone_id === zone.id) continue;
      const poly = L.polygon(zone.points, { color: primary, weight: 2, fillOpacity: 0.2 });
      poly.bindTooltip(zone.name, { permanent: true, direction: "center", className: "zone-label" });
      poly.on("click", () => this._startEdit(zone));
      poly.addTo(this._zoneLayer);
    }
  }

  _drawTrackers() {
    if (!this._trackerLayer || !this._trackers) return;
    // hass updates on every state change in HA; only redraw when our trackers moved
    const signature = JSON.stringify(
      this._trackers.map((id) => {
        const s = this._hass.states[id];
        return s && [s.state, s.attributes.latitude, s.attributes.longitude, s.attributes.gps_accuracy];
      })
    );
    if (signature === this._trackerSignature) return;
    this._trackerSignature = signature;
    this._trackerLayer.clearLayers();
    for (const entityId of this._trackers) {
      const state = this._hass.states[entityId];
      if (!state) continue;
      const { latitude, longitude, gps_accuracy } = state.attributes;
      if (latitude == null || longitude == null) continue;
      if (gps_accuracy) {
        L.circle([latitude, longitude], {
          radius: gps_accuracy, color: "#e91e63", weight: 1, fillOpacity: 0.08, interactive: false,
        }).addTo(this._trackerLayer);
      }
      L.circleMarker([latitude, longitude], {
        radius: 7, color: "white", weight: 2, fillColor: "#e91e63", fillOpacity: 1,
      })
        .bindTooltip(`${state.attributes.friendly_name || entityId}: ${state.state}`)
        .addTo(this._trackerLayer);
    }
  }

  _drawEdit() {
    this._editLayer.clearLayers();
    const edit = this._edit;
    // double-click removes a corner while editing, so it must not zoom then
    if (!edit) {
      this._map.doubleClickZoom.enable();
      return;
    }
    this._map.doubleClickZoom.disable();
    const color = "#ff9800";
    const poly = L.polygon(edit.points, { color, weight: 3, fillOpacity: 0.25, interactive: false }).addTo(
      this._editLayer
    );

    const handle = (cls, latlng, html = "") =>
      L.marker(latlng, {
        draggable: true,
        icon: L.divIcon({ className: "", html: `<div class="${cls}">${html}</div>`, iconSize: [0, 0] }),
      }).addTo(this._editLayer);

    // corners
    edit.points.forEach((pt, i) => {
      const m = handle("handle", pt);
      m.on("drag", (ev) => {
        const { lat, lng } = ev.target.getLatLng();
        this._moveCorner(i, lat, lng);
        poly.setLatLngs(edit.points);
      });
      m.on("dragend", () => this._afterChange());
      const remove = (ev) => {
        L.DomEvent.stop(ev);
        if (edit.rect || edit.points.length <= 3) return;
        edit.points.splice(i, 1);
        this._afterChange();
      };
      m.on("contextmenu", remove);
      m.on("dblclick", remove);
    });

    // midpoints: drag to insert a corner
    if (!edit.rect) {
      edit.points.forEach((pt, i) => {
        const next = edit.points[(i + 1) % edit.points.length];
        const m = handle("mid", [(pt[0] + next[0]) / 2, (pt[1] + next[1]) / 2]);
        let inserted = false;
        m.on("dragstart", () => {
          edit.points.splice(i + 1, 0, [pt[0], pt[1]]);
          inserted = true;
        });
        m.on("drag", (ev) => {
          if (!inserted) return;
          const { lat, lng } = ev.target.getLatLng();
          edit.points[i + 1] = [lat, lng];
          poly.setLatLngs(edit.points);
        });
        m.on("dragend", () => this._afterChange());
      });
    }

    // move handle at the centre
    const center = () => {
      const n = edit.points.length;
      return [edit.points.reduce((s, p) => s + p[0], 0) / n, edit.points.reduce((s, p) => s + p[1], 0) / n];
    };
    const mover = handle("move", center(), "✥");
    let start = null;
    mover.on("dragstart", (ev) => {
      start = { at: ev.target.getLatLng(), points: edit.points.map((p) => [...p]) };
    });
    mover.on("drag", (ev) => {
      const { lat, lng } = ev.target.getLatLng();
      const dLat = lat - start.at.lat;
      const dLon = lng - start.at.lng;
      edit.points = start.points.map(([a, b]) => [a + dLat, b + dLon]);
      poly.setLatLngs(edit.points);
    });
    mover.on("dragend", () => this._afterChange());
  }

  _moveCorner(i, lat, lon) {
    const edit = this._edit;
    if (!edit.rect) {
      edit.points[i] = [lat, lon];
      return;
    }
    // points are [lat1,lon1],[lat1,lon2],[lat2,lon2],[lat2,lon1]: keep the opposite corner fixed
    const opposite = edit.points[(i + 2) % 4];
    const sameLat = i % 2 === 0 ? (i + 1) % 4 : (i + 3) % 4;
    const sameLon = i % 2 === 0 ? (i + 3) % 4 : (i + 1) % 4;
    edit.points[i] = [lat, lon];
    edit.points[sameLat] = [lat, opposite[1]];
    edit.points[sameLon] = [opposite[0], lon];
  }

  _afterChange() {
    this._edit.dirty = true;
    this._message = null;
    this._drawEdit();
    this._renderSide();
  }

  // ---- editing ----------------------------------------------------------

  _confirmDiscard() {
    return !this._edit?.dirty || confirm(this._t("confirm_discard"));
  }

  _startEdit(zone) {
    if (this._edit?.zone_id === zone.id || !this._confirmDiscard()) return;
    this._edit = {
      zone_id: zone.id,
      name: zone.name,
      points: zone.points.map((p) => [...p]),
      rect: isAxisRectangle(zone.points),
      dirty: false,
    };
    this._message = null;
    this._map.fitBounds(L.latLngBounds(zone.points).pad(0.5), { maxZoom: 19 });
    this._drawZones();
    this._drawEdit();
    this._renderSide(true);
  }

  _newZone() {
    if (!this._confirmDiscard()) return;
    const b = this._map.getBounds();
    const c = b.getCenter();
    const dLat = (b.getNorth() - b.getSouth()) * 0.15;
    const dLon = (b.getEast() - b.getWest()) * 0.15;
    this._edit = {
      zone_id: null,
      name: "",
      points: rectangleFrom(c.lat - dLat, c.lng - dLon, c.lat + dLat, c.lng + dLon),
      rect: true,
      dirty: true,
    };
    this._message = null;
    this._drawZones();
    this._drawEdit();
    this._renderSide(true);
  }

  _cancel() {
    if (!this._confirmDiscard()) return;
    this._edit = null;
    this._message = null;
    this._drawZones();
    this._drawEdit();
    this._renderSide();
  }

  async _save() {
    const edit = this._edit;
    const name = (edit.name || "").trim();
    if (!name) {
      this._message = { error: true, text: this._t("err_name") };
      this._renderSide();
      return;
    }
    const msg = { type: "shape_zones/save_zone", name, points: edit.points.map(([a, b]) => [round(a), round(b)]) };
    if (edit.zone_id) msg.zone_id = edit.zone_id;
    try {
      const zone = await this._hass.callWS(msg);
      this._edit = null;
      this._message = { error: false, text: `${this._t("saved")}: ${zone.name}` };
      this._drawEdit();
      await this._load();
    } catch (err) {
      this._message = {
        error: true,
        text: err.code === "name_exists" ? this._t("err_name_exists") : this._t("err_generic", { msg: err.message }),
      };
      this._renderSide();
    }
  }

  async _delete() {
    const edit = this._edit;
    if (!edit?.zone_id || !confirm(this._t("confirm_delete", { name: edit.name }))) return;
    try {
      await this._hass.callWS({ type: "shape_zones/delete_zone", zone_id: edit.zone_id });
      this._edit = null;
      this._message = null;
      this._drawEdit();
      await this._load();
    } catch (err) {
      this._message = { error: true, text: this._t("err_generic", { msg: err.message }) };
      this._renderSide();
    }
  }

  // ---- side panel -------------------------------------------------------

  _renderSide(focusName = false) {
    const side = this._side;
    side.innerHTML = "";
    const el = (tag, attrs = {}, text) => {
      const e = document.createElement(tag);
      Object.assign(e, attrs);
      if (text != null) e.textContent = text;
      return e;
    };

    if (this._error) {
      side.append(el("p", { className: "error" }, this._error));
      return;
    }

    const edit = this._edit;
    if (edit) {
      side.append(el("h2", {}, edit.zone_id ? edit.name || this._t("name") : this._t("new_zone")));
      side.append(el("label", { htmlFor: "name" }, this._t("name")));
      const input = el("input", { type: "text", id: "name", value: edit.name });
      input.addEventListener("input", () => {
        edit.name = input.value;
        edit.dirty = true;
      });
      input.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") this._save();
      });
      side.append(input);

      const check = el("label", { className: "check" });
      const box = el("input", { type: "checkbox", checked: edit.rect });
      box.addEventListener("change", () => {
        if (box.checked) {
          const lats = edit.points.map((p) => p[0]);
          const lons = edit.points.map((p) => p[1]);
          edit.points = rectangleFrom(Math.min(...lats), Math.min(...lons), Math.max(...lats), Math.max(...lons));
        }
        edit.rect = box.checked;
        this._afterChange();
      });
      check.append(box, document.createTextNode(this._t("keep_rectangle")));
      side.append(check);

      side.append(el("p", { className: "muted" }, this._t(edit.rect ? "hint_rect" : "hint_free")));
      side.append(
        el("p", { className: "muted" }, `${this._t("points", { n: edit.points.length })} · ${Math.round(areaM2(edit.points))} m²`)
      );

      const row = el("div", { className: "row" });
      const save = el("button", { className: "primary" }, this._t("save"));
      save.addEventListener("click", () => this._save());
      const cancel = el("button", {}, this._t("cancel"));
      cancel.addEventListener("click", () => this._cancel());
      row.append(save, cancel);
      if (edit.zone_id) {
        const del = el("button", { className: "danger" }, this._t("delete"));
        del.addEventListener("click", () => this._delete());
        row.append(del);
      }
      side.append(row);
      if (this._message) side.append(el("p", { className: this._message.error ? "error" : "ok" }, this._message.text));
      if (focusName) setTimeout(() => input.focus(), 0);
      return;
    }

    const add = el("button", { className: "primary" }, `+ ${this._t("new_zone")}`);
    add.addEventListener("click", () => this._newZone());
    side.append(add);
    if (this._message) side.append(el("p", { className: this._message.error ? "error" : "ok" }, this._message.text));

    side.append(el("h2", {}, this._t("zones")));
    if (!this._zones.length) side.append(el("p", { className: "muted" }, this._t("no_zones")));
    for (const zone of this._zones) {
      const item = el("div", { className: "zone" });
      item.append(el("span", {}, zone.name), el("small", {}, `${Math.round(areaM2(zone.points))} m²`));
      item.addEventListener("click", () => this._startEdit(zone));
      side.append(item);
    }
  }
}

if (!customElements.get("shape-zones-panel")) {
  customElements.define("shape-zones-panel", ShapeZonesPanel);
}
