"""Emissions inventory -> pollutant / heat / noise fields.

Each land-use driver carries an *emission factor* for each variable. We sum
the emissions and spread them through space with a Gaussian dispersion kernel:

* PM2.5  — long range, **anisotropic**: the plume stretches downwind. In the
           valley preset a wintertime **inversion** multiplies the trapped
           concentration and makes transport more stagnant (near isotropic).
* heat   — moderate, isotropic smoothing; parks and water actively cool.
* noise  — very local (sharp decay); freeways and industry dominate.

Fields are rescaled to realistic ranges so colour scales and scores are
comparable across scenarios:

    PM2.5   5 – 55  ug/m^3
    heat   -2 – +7  deg C anomaly above the rural baseline
    noise  42 – 84  dB(A)

This module is pure numpy; `build_fields` is the single entry point used by
``city.generate_scenario``.
"""

from __future__ import annotations

import numpy as np

# display metadata used by the UI and colour scales
VARIABLES = {
    "PM25":  dict(label="PM2.5",       unit="ug/m3", lo=5.0,  hi=55.0,
                  colors=["#ffffcc", "#fd8d3c", "#bd0026"]),
    "heat":  dict(label="Urban heat",  unit="degC",  lo=-2.0, hi=7.0,
                  colors=["#2c7bb6", "#ffffbf", "#d7191c"]),
    "noise": dict(label="Noise",       unit="dB(A)", lo=42.0, hi=84.0,
                  colors=["#1a9850", "#fee08b", "#762a83"]),
}

# emission factors: contribution of each unit driver to each variable
_EMIT = {
    "PM25":  dict(ind=40.0, fw=26.0, dt=8.0,  res=6.0,  park=0.0,  water=0.0),
    "heat":  dict(ind=3.0,  fw=2.0,  dt=5.0,  res=1.6,  park=-3.0, water=-4.0),
    "noise": dict(ind=20.0, fw=35.0, dt=15.0, res=5.0,  park=0.0,  water=-5.0),
}


def _iso_kernel(dist, L):
    return np.exp(-0.5 * (dist / L) ** 2)


def _wind_kernel(dx, dy, dist, wind, L_down, L_cross, L_up):
    """Anisotropic kernel: wider downwind, narrow across- and up-wind."""
    along = dx * wind[0] + dy * wind[1]
    cross = np.sqrt(np.maximum(dist ** 2 - along ** 2, 0.0))
    pos = np.maximum(along, 0.0)   # downwind
    neg = np.minimum(along, 0.0)   # upwind
    d2 = (pos / L_down) ** 2 + (neg / L_up) ** 2 + (cross / L_cross) ** 2
    return np.exp(-0.5 * d2)


def _rescale(raw, lo, hi, plo=2, phi=98):
    """Map raw field to [lo, hi] via robust percentile stretch."""
    a, b = np.percentile(raw, [plo, phi])
    if b - a < 1e-9:
        return np.full_like(raw, (lo + hi) / 2.0)
    scaled = (raw - a) / (b - a)
    return lo + np.clip(scaled, 0.0, 1.0) * (hi - lo)


def _emission_vector(d, var):
    e = _EMIT[var]
    return (e["ind"] * d["ind"] + e["fw"] * d["fw"] + e["dt"] * d["dt"]
            + e["res"] * d["res"] + e["park"] * d["park"]
            + e["water"] * d["water"])


def build_fields(preset_key, d, xy, neighbors, rng):
    """Return dict with PM25, heat, noise, population, vulnerability arrays."""
    # numpy 2.0 + Apple Accelerate BLAS emits spurious FP warnings on matmul;
    # the results are correct, so quiet them for the dispersion maths below.
    with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
        return _build_fields(preset_key, d, xy, neighbors, rng)


def _build_fields(preset_key, d, xy, neighbors, rng):
    n = xy.shape[0]
    dx = np.subtract.outer(xy[:, 0], xy[:, 0])   # receptor - source
    dy = np.subtract.outer(xy[:, 1], xy[:, 1])
    dist = np.hypot(dx, dy)

    # a gently correlated random field for texture (shared basis, scaled later)
    noise_seed = rng.normal(0.0, 1.0, size=n)
    texture = _iso_kernel(dist, 500.0) @ noise_seed
    texture = (texture - texture.mean()) / (texture.std() + 1e-9)

    out = {}

    # --- PM2.5: anisotropic transport + optional inversion trapping --------
    if preset_key == "valley":
        Kpm = _wind_kernel(dx, dy, dist, d["wind"],
                           L_down=1200.0, L_cross=1000.0, L_up=900.0)
    else:
        Kpm = _wind_kernel(dx, dy, dist, d["wind"],
                           L_down=1800.0, L_cross=700.0, L_up=450.0)
    pm = Kpm @ _emission_vector(d, "PM25")
    if preset_key == "valley":
        pm = pm * (1.0 + 1.6 * d["basin"])   # inversion piles PM up in the bowl
    pm = pm + 0.06 * pm.std() * texture
    out["PM25"] = _rescale(pm, VARIABLES["PM25"]["lo"], VARIABLES["PM25"]["hi"])

    # --- heat: isotropic, parks/water cool --------------------------------
    Kh = _iso_kernel(dist, 900.0)
    heat = Kh @ _emission_vector(d, "heat")
    heat = heat + 0.05 * heat.std() * texture
    out["heat"] = _rescale(heat, VARIABLES["heat"]["lo"], VARIABLES["heat"]["hi"])

    # --- noise: local, sharp ----------------------------------------------
    Kn = _iso_kernel(dist, 300.0)
    noise = Kn @ _emission_vector(d, "noise")
    noise = noise + 0.05 * noise.std() * texture
    out["noise"] = _rescale(noise, VARIABLES["noise"]["lo"], VARIABLES["noise"]["hi"])

    # --- population: residential + downtown, zero over water --------------
    pop_raw = (1.0 * d["res"] + 1.3 * d["dt"] + 0.3 * d["fw"]) * (1 - d["water"])
    pop = _rescale(pop_raw, 150.0, 14000.0, plo=5, phi=99) * (1 - d["water"])
    out["population"] = pop

    # --- vulnerability / EJ index (0..1): legacy siting near industry/road -
    vuln_raw = (0.6 * d["ind"] + 0.5 * d["fw"] + 0.3 * (1 - d["park"])
                + 0.25 * d["res"])
    vuln_raw = vuln_raw + 0.2 * texture
    vuln = _rescale(vuln_raw, 0.0, 1.0, plo=5, phi=95) * (1 - d["water"])
    out["vulnerability"] = vuln

    return out
