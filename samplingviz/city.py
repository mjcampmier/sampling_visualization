"""Procedural, seeded cities on a hexagonal grid.

We build a rectangular block of pointy-top hexes in an "odd-r" offset layout,
convert to axial coordinates for trivial 6-neighbour / k-ring lookups, and lay
the whole thing over a real city centre so the map has a believable
geographic scale. Land use is generated from a handful of geometric
primitives (a downtown core, industrial blobs, a freeway corridor, parks, a
coastline) that differ by preset. A random *seed* jitters the layout so every
student / group can get their own version of the same city.

Everything downstream (the emissions inventory, the sampling designs, the
scoring) is driven by the arrays produced here, so this module has no
dependency on Streamlit and can be exercised from a plain Python shell:

    >>> from samplingviz.city import generate_scenario
    >>> sc = generate_scenario("coastal", seed=42)
    >>> sc["hexes"].head()
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .inventory import build_fields

# --- grid geometry -------------------------------------------------------

COLS = 24          # hexes east-west
ROWS = 18          # hexes north-south
HEX_SIZE_M = 260.0  # centre-to-corner, metres  (~450 m flat-to-flat)

# pointy-top hex: horizontal spacing sqrt(3)*size, vertical spacing 1.5*size
_SQRT3 = math.sqrt(3.0)
M_PER_DEG_LAT = 111_320.0

# the six axial neighbour directions for pointy-top hexes
_AXIAL_DIRS = [(+1, 0), (+1, -1), (0, -1), (-1, 0), (-1, +1), (0, +1)]


@dataclass(frozen=True)
class Preset:
    key: str
    name: str
    blurb: str
    center_lat: float
    center_lon: float


PRESETS = {
    "coastal": Preset(
        "coastal", "Coastal Port",
        "A bay on the west edge, a container port + industry on the "
        "waterfront, downtown just inland, an onshore (westerly) wind pushing "
        "plumes over the residential east side.",
        37.805, -122.272,  # ~ Oakland, CA
    ),
    "valley": Preset(
        "valley", "Valley Basin",
        "A bowl ringed by hills with a wintertime inversion that traps "
        "pollution over the whole basin. Weak, stagnant winds; two industrial "
        "districts and a diagonal freeway.",
        40.760, -111.890,  # ~ Salt Lake City, UT
    ),
    "grid": Preset(
        "grid", "Grid + Freeway",
        "A flat grid city with a freeway interchange (one N-S, one E-W "
        "interstate) crossing at a downtown core, scattered industry, and a "
        "steady south-westerly wind.",
        33.450, -112.070,  # ~ Phoenix, AZ
    ),
}

DEFAULT_PRESET = "coastal"


# --- small uv-space helpers ---------------------------------------------

def _gauss(U, V, cu, cv, su, sv):
    return np.exp(-0.5 * (((U - cu) / su) ** 2 + ((V - cv) / sv) ** 2))


def _seg_dist(U, V, p0, p1):
    """Distance from each (U,V) point to the line segment p0->p1 (uv space)."""
    x0, y0 = p0
    x1, y1 = p1
    dx, dy = x1 - x0, y1 - y0
    seg_len2 = dx * dx + dy * dy + 1e-12
    t = ((U - x0) * dx + (V - y0) * dy) / seg_len2
    t = np.clip(t, 0.0, 1.0)
    projx = x0 + t * dx
    projy = y0 + t * dy
    return np.hypot(U - projx, V - projy)


def _smooth_field(idx_neighbors, values, passes=2, keep=0.5):
    """Cheap diffusion: blend each hex toward its neighbours' mean."""
    out = values.astype(float).copy()
    for _ in range(passes):
        nxt = out.copy()
        for i, nb in enumerate(idx_neighbors):
            if nb:
                nxt[i] = keep * out[i] + (1 - keep) * float(np.mean(out[nb]))
        out = nxt
    return out


# --- land-use primitives per preset -------------------------------------

def _land_use_drivers(preset_key, U, V, rng):
    """Return continuous [0,1] driver arrays + wind + inversion for a preset.

    Keys: dt (downtown/built core), ind (industry), park, fw (freeway
    proximity), water (0/1 flag), basin (inversion-trapping weight 0..1),
    wind (unit vector pushing plumes downwind).
    """
    j = lambda s=0.035: rng.normal(0.0, s)  # center jitter

    water = np.zeros_like(U)
    basin = np.zeros_like(U)

    if preset_key == "coastal":
        # wavy coastline on the west edge -> bay is water
        coast = 0.17 + 0.06 * np.sin(V * math.pi * 1.5)
        water = (U < coast).astype(float)
        ind = _gauss(U, V, 0.24 + j(), 0.52 + j(), 0.09, 0.14)       # port
        dt = _gauss(U, V, 0.44 + j(), 0.44 + j(), 0.10, 0.10)        # downtown
        park = (_gauss(U, V, 0.72 + j(), 0.28 + j(), 0.09, 0.09)
                + 0.9 * _gauss(U, V, 0.86 + j(), 0.74 + j(), 0.08, 0.08))
        fw = np.exp(-0.5 * (_seg_dist(U, V, (0.30, 0.0), (0.52, 1.0)) / 0.028) ** 2)
        wind = np.array([1.0, 0.1])  # onshore, west -> east

    elif preset_key == "valley":
        ind = (_gauss(U, V, 0.30 + j(), 0.70 + j(), 0.10, 0.10)
               + 0.9 * _gauss(U, V, 0.66 + j(), 0.58 + j(), 0.09, 0.09))
        dt = _gauss(U, V, 0.50 + j(), 0.46 + j(), 0.11, 0.11)
        park = _gauss(U, V, 0.20 + j(), 0.30 + j(), 0.08, 0.08)
        fw = np.maximum(
            np.exp(-0.5 * (_seg_dist(U, V, (0.08, 0.20), (0.92, 0.82)) / 0.026) ** 2),
            np.exp(-0.5 * (_seg_dist(U, V, (0.55, 0.0), (0.48, 1.0)) / 0.024) ** 2),
        )
        # inversion bowl: deepest (most trapping) in the low centre
        basin = _gauss(U, V, 0.5, 0.55, 0.42, 0.42)
        wind = np.array([0.3, 0.2])  # weak, stagnant

    else:  # "grid"
        fw = np.maximum(
            np.exp(-0.5 * (_seg_dist(U, V, (0.0, 0.5), (1.0, 0.5)) / 0.024) ** 2),
            np.exp(-0.5 * (_seg_dist(U, V, (0.5, 0.0), (0.5, 1.0)) / 0.024) ** 2),
        )
        dt = _gauss(U, V, 0.50 + j(), 0.50 + j(), 0.09, 0.09)
        ind = (0.9 * _gauss(U, V, 0.76 + j(), 0.26 + j(), 0.08, 0.08)
               + 0.9 * _gauss(U, V, 0.24 + j(), 0.80 + j(), 0.08, 0.08))
        park = (_gauss(U, V, 0.20 + j(), 0.22 + j(), 0.07, 0.07)
                + _gauss(U, V, 0.80 + j(), 0.80 + j(), 0.07, 0.07))
        wind = np.array([0.8, 0.6])  # steady south-westerly

    # normalise directional wind to a unit vector
    wind = wind / (np.linalg.norm(wind) + 1e-9)

    clip01 = lambda a: np.clip(a, 0.0, 1.0)
    return {
        "dt": clip01(dt) * (1 - water),
        "ind": clip01(ind) * (1 - water),
        "park": clip01(park) * (1 - water),
        "fw": clip01(fw) * (1 - water),
        "water": water,
        "basin": basin,
        "wind": wind,
    }


# --- land-use classification --------------------------------------------

LAND_USES = ["water", "freeway", "industrial", "park", "downtown", "residential"]
LAND_USE_COLORS = {
    "water": "#9ecae1",
    "freeway": "#636363",
    "industrial": "#8c6d31",
    "park": "#74c476",
    "downtown": "#d9a0d9",
    "residential": "#fdd0a2",
}


def _classify(d):
    n = len(d["dt"])
    cat = np.array(["residential"] * n, dtype=object)
    res_bg = np.clip(1 - d["ind"] - d["fw"] - d["dt"] - d["park"] - d["water"], 0, 1)
    # priority order: water > freeway > industry > park > downtown > residential
    cat[d["dt"] > 0.40] = "downtown"
    cat[d["park"] > 0.45] = "park"
    cat[d["ind"] > 0.45] = "industrial"
    cat[d["fw"] > 0.45] = "freeway"
    cat[d["water"] > 0.5] = "water"
    return cat, res_bg


# --- the public builder --------------------------------------------------

def _build_grid(center_lat, center_lon):
    """Build hex geometry. Returns dict of parallel arrays + neighbour lists."""
    rows, cols = ROWS, COLS
    n = rows * cols
    row = np.repeat(np.arange(rows), cols)
    col = np.tile(np.arange(cols), rows)

    # odd-r offset -> pixel (metres)
    x = HEX_SIZE_M * _SQRT3 * (col + 0.5 * (row & 1))
    y = HEX_SIZE_M * 1.5 * row
    x = x - x.mean()
    y = y - y.mean()

    m_per_deg_lon = M_PER_DEG_LAT * math.cos(math.radians(center_lat))
    lat = center_lat + (-y) / M_PER_DEG_LAT          # row 0 is north (top)
    lon = center_lon + x / m_per_deg_lon

    # hexagon corner polygons (lat, lon), pointy-top
    corner_ang = np.radians(60 * np.arange(6) + 30)
    cx = HEX_SIZE_M * np.cos(corner_ang)
    cy = HEX_SIZE_M * np.sin(corner_ang)
    polygons = []
    for i in range(n):
        plat = center_lat + (-(y[i] + cy)) / M_PER_DEG_LAT
        plon = center_lon + (x[i] + cx) / m_per_deg_lon
        polygons.append(list(zip(plat.tolist(), plon.tolist())))

    # neighbours via axial coordinates
    q = col - (row - (row & 1)) // 2
    rr = row
    axial_to_idx = {(int(q[i]), int(rr[i])): i for i in range(n)}
    neighbors = []
    for i in range(n):
        nb = []
        for dq, dr in _AXIAL_DIRS:
            key = (int(q[i]) + dq, int(rr[i]) + dr)
            j = axial_to_idx.get(key)
            if j is not None:
                nb.append(j)
        neighbors.append(nb)

    u = col / (cols - 1)
    v = row / (rows - 1)
    return dict(n=n, row=row, col=col, x=x, y=y, lat=lat, lon=lon,
                polygons=polygons, neighbors=neighbors, u=u, v=v,
                m_per_deg_lon=m_per_deg_lon)


def generate_scenario(preset_key=DEFAULT_PRESET, seed=42):
    """Build a full scenario: geometry, land use, and the three fields.

    Returns a dict with:
      preset   : Preset
      hexes    : DataFrame (one row per hex) with geometry, land use,
                 population, vulnerability, and the PM25/heat/noise fields
      polygons : list[list[(lat,lon)]]  hex boundaries
      neighbors: list[list[int]]        6-neighbour adjacency
      xy       : (n,2) float array of centres in metres
      land_ids : np.ndarray of hex indices that are *not* water
    """
    preset = PRESETS[preset_key]
    rng = np.random.default_rng(seed)
    g = _build_grid(preset.center_lat, preset.center_lon)

    U, V = g["u"], g["v"]
    d = _land_use_drivers(preset_key, U, V, rng)
    cat, res_bg = _classify(d)
    d["res"] = res_bg

    xy = np.column_stack([g["x"], g["y"]])

    # emissions inventory -> fields (PM2.5, heat, noise) + pop + vulnerability
    fields = build_fields(preset_key, d, xy, g["neighbors"], rng)

    hexes = pd.DataFrame({
        "idx": np.arange(g["n"]),
        "row": g["row"], "col": g["col"],
        "lat": g["lat"], "lon": g["lon"],
        "u": U, "v": V,
        "land_use": cat,
        "is_water": d["water"] > 0.5,
        "drv_dt": d["dt"], "drv_ind": d["ind"], "drv_park": d["park"],
        "drv_fw": d["fw"], "drv_res": res_bg, "basin": d["basin"],
        "population": fields["population"],
        "vulnerability": fields["vulnerability"],
        "PM25": fields["PM25"],
        "heat": fields["heat"],
        "noise": fields["noise"],
    })

    land_ids = hexes.index[~hexes["is_water"]].to_numpy()

    return dict(
        preset=preset,
        seed=int(seed),
        hexes=hexes,
        polygons=g["polygons"],
        neighbors=g["neighbors"],
        xy=xy,
        land_ids=land_ids,
        hex_spacing_m=HEX_SIZE_M * _SQRT3,
        wind=d["wind"],
    )
