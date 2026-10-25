"""Folium map construction for the Streamlit app.

The hex grid is drawn as a single GeoJSON layer (fast, one draw call for the
whole city) coloured by whichever variable is on display. Student sensors and
an optional algorithm overlay are drawn as circle markers on top; hotspots can
be outlined. ``nearest_land_hex`` turns a map click (lat/lng) back into a hex
index so students can place sensors by clicking.
"""

from __future__ import annotations

import math

import branca.colormap as cm
import folium
import numpy as np

from .city import LAND_USE_COLORS
from .inventory import VARIABLES

# display options beyond the three measured fields
_EXTRA_DISPLAY = {
    "population":    dict(label="Population", unit="ppl/km2",
                          colors=["#f7fbff", "#6baed6", "#08306b"]),
    "vulnerability": dict(label="Vulnerability (EJ)", unit="index",
                          colors=["#ffffff", "#fb6a4a", "#67000d"], lo=0.0, hi=1.0),
}


def display_options():
    """(key -> label) for the display-variable selector."""
    opts = {k: f"{v['label']} ({v['unit']})" for k, v in VARIABLES.items()}
    opts["population"] = "Population (ppl/km2)"
    opts["vulnerability"] = "Vulnerability / EJ (0-1)"
    opts["land_use"] = "Land use (categories)"
    return opts


def _colormap_for(display_var, values):
    if display_var in VARIABLES:
        meta = VARIABLES[display_var]
        lo, hi = meta["lo"], meta["hi"]
        colors, label = meta["colors"], f"{meta['label']} ({meta['unit']})"
    else:
        meta = _EXTRA_DISPLAY[display_var]
        lo = meta.get("lo", float(np.nanmin(values)))
        hi = meta.get("hi", float(np.nanmax(values)))
        colors, label = meta["colors"], f"{meta['label']} ({meta['unit']})"
    scale = cm.LinearColormap(colors, vmin=lo, vmax=hi, caption=label)
    return scale


def build_map(scenario, display_var, student_ids, overlay_ids=None,
              overlay_color="#6a3d9a", overlay_label="method",
              show_hotspots=False, basemap=True):
    preset = scenario["preset"]
    hexes = scenario["hexes"]
    polygons = scenario["polygons"]

    m = folium.Map(
        location=[preset.center_lat, preset.center_lon],
        zoom_start=12,
        # OpenStreetMap needs no API key (CartoDB now does); None = clean,
        # offline-friendly blank canvas so the hexes stand on their own.
        tiles="OpenStreetMap" if basemap else None,
        control_scale=True,
    )

    categorical = display_var == "land_use"
    values = None if categorical else hexes[display_var].to_numpy()
    scale = None if categorical else _colormap_for(display_var, values)

    def _color(i):
        if categorical:
            return LAND_USE_COLORS[hexes.at[i, "land_use"]]
        if hexes.at[i, "is_water"]:
            return LAND_USE_COLORS["water"]
        return scale(values[i])

    features = []
    for i, poly in enumerate(polygons):
        tip = (f"<b>{hexes.at[i,'land_use'].title()}</b><br>"
               f"PM2.5: {hexes.at[i,'PM25']:.0f} ug/m3<br>"
               f"Heat: {hexes.at[i,'heat']:+.1f} degC<br>"
               f"Noise: {hexes.at[i,'noise']:.0f} dB<br>"
               f"Pop: {hexes.at[i,'population']:.0f} | Vuln: "
               f"{hexes.at[i,'vulnerability']:.2f}")
        features.append({
            "type": "Feature",
            "properties": {"color": _color(i), "tip": tip},
            "geometry": {
                "type": "Polygon",
                # GeoJSON is (lon, lat)
                "coordinates": [[[lon, lat] for lat, lon in poly]],
            },
        })

    folium.GeoJson(
        {"type": "FeatureCollection", "features": features},
        style_function=lambda f: {
            "fillColor": f["properties"]["color"],
            "color": "#555555",
            "weight": 0.4,
            "fillOpacity": 0.70,
        },
        highlight_function=lambda f: {"weight": 2.0, "color": "#111111"},
        tooltip=folium.GeoJsonTooltip(fields=["tip"], labels=False,
                                      sticky=True),
        name="City",
    ).add_to(m)

    if show_hotspots and not categorical and display_var in VARIABLES:
        from .scoring import hotspot_mask
        hot = set(int(i) for i in hotspot_mask(scenario, display_var))
        hot_feats = [{
            "type": "Feature", "properties": {},
            "geometry": {"type": "Polygon",
                         "coordinates": [[[lon, lat] for lat, lon in polygons[i]]]},
        } for i in hot]
        folium.GeoJson(
            {"type": "FeatureCollection", "features": hot_feats},
            style_function=lambda f: {"fillOpacity": 0.0, "color": "#111111",
                                      "weight": 1.6, "dashArray": "3,3"},
            name="Hotspots",
        ).add_to(m)

    # algorithm overlay first (so student markers sit on top)
    for i in (overlay_ids or []):
        folium.CircleMarker(
            location=[hexes.at[int(i), "lat"], hexes.at[int(i), "lon"]],
            radius=7, color=overlay_color, weight=2, fill=True,
            fill_color=overlay_color, fill_opacity=0.55,
            tooltip=f"{overlay_label} sensor",
        ).add_to(m)

    for i in (student_ids or []):
        folium.CircleMarker(
            location=[hexes.at[int(i), "lat"], hexes.at[int(i), "lon"]],
            radius=6, color="#111111", weight=2, fill=True,
            fill_color="#2b8cbe", fill_opacity=0.95,
            tooltip="your sensor (click to remove)",
        ).add_to(m)

    if scale is not None:
        scale.add_to(m)
    return m


def nearest_land_hex(scenario, lat, lng, max_hexes=1.6):
    """Snap a map click to the nearest land hex; None if the click is too far."""
    hexes = scenario["hexes"]
    land = scenario["land_ids"]
    coslat = math.cos(math.radians(lat))
    dlat = hexes.loc[land, "lat"].to_numpy() - lat
    dlon = (hexes.loc[land, "lon"].to_numpy() - lng) * coslat
    d = np.hypot(dlat, dlon)
    k = int(np.argmin(d))
    # guard: ignore clicks farther than ~max_hexes spacings from any hex
    spacing_deg = scenario["hex_spacing_m"] / 111_320.0
    if d[k] > max_hexes * spacing_deg:
        return None
    return int(land[k])
