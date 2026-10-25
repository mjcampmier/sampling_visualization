"""Scoring a sensor placement.

Given a set of sensor hexes we ask four questions a real monitoring-network
designer cares about:

1. **Reconstruction** — if we interpolate the network's readings back across
   the whole city (inverse-distance weighting), how close is the estimated
   field to the truth?  Reported as R^2 -> a 0-100 score, plus RMSE in native
   units. This is the "representativeness" of the network.
2. **Hotspot recall** — of the worst 10% of hexes for a variable, how many sit
   within one hex of a sensor?  Did we actually *catch* the problem areas?
3. **Spatial coverage** — what fraction of the city is within sensing range of
   some sensor?  (A pure geometry metric, same for every variable.)
4. **Equity gap** — population-weighted coverage of high-vulnerability areas
   minus that of low-vulnerability areas. Positive = vulnerable communities are
   *under*-monitored. Environmental-justice lens.

``score_placement`` returns per-variable reconstruction/hotspot numbers plus
the shared coverage/equity numbers and a single blended ``overall`` 0-100.
"""

from __future__ import annotations

import numpy as np

from .inventory import VARIABLES

HOTSPOT_Q = 0.90          # top 10% of a field are "hotspots"


def _dist_matrix(xy, idx_a, idx_b):
    a = xy[idx_a]
    b = xy[idx_b]
    return np.sqrt(((a[:, None, :] - b[None, :, :]) ** 2).sum(axis=2))


def _idw_estimate(values_at_sensors, dist_land_to_sensor, power=2.0):
    """Inverse-distance-weighted estimate at every land hex."""
    d = dist_land_to_sensor.copy()
    on_sensor = d < 1e-6
    d[d < 1e-6] = 1e-6
    w = 1.0 / d ** power
    est = (w * values_at_sensors[None, :]).sum(axis=1) / w.sum(axis=1)
    # exact value where a sensor sits on the hex
    rows = np.where(on_sensor.any(axis=1))[0]
    for r in rows:
        est[r] = values_at_sensors[np.argmax(on_sensor[r])]
    return est


def score_placement(scenario, sensor_ids, variables=("PM25", "heat", "noise")):
    """Score a placement. Returns a flat dict of metrics (see module docs)."""
    hexes = scenario["hexes"]
    xy = scenario["xy"]
    land = scenario["land_ids"]
    spacing = scenario["hex_spacing_m"]
    sensors = [int(s) for s in sensor_ids if not bool(hexes.at[int(s), "is_water"])]

    out = {"n_sensors": len(sensors)}
    if len(sensors) == 0:
        for v in variables:
            out[f"{v}_recon"] = 0.0
            out[f"{v}_rmse"] = float("nan")
            out[f"{v}_hotspot"] = 0.0
        out.update(coverage=0.0, pop_coverage=0.0, equity_gap=100.0,
                   blindspot_m=float("nan"), overall=0.0)
        return out

    dls = _dist_matrix(xy, land, sensors)          # land x sensors (metres)
    nearest = dls.min(axis=1)                       # nearest-sensor distance
    sense_r = 1.5 * spacing                          # "monitored" if within ~1 hex
    cover_r = 2.5 * spacing                          # "covered" if within ~2 hexes

    recon_scores = []
    hotspot_scores = []
    for v in variables:
        truth = hexes.loc[land, v].to_numpy()
        at_sensor = hexes.loc[sensors, v].to_numpy()
        est = _idw_estimate(at_sensor, dls)
        ss_res = float(((truth - est) ** 2).sum())
        ss_tot = float(((truth - truth.mean()) ** 2).sum()) + 1e-9
        r2 = 1.0 - ss_res / ss_tot
        out[f"{v}_recon"] = round(100.0 * float(np.clip(r2, 0.0, 1.0)), 1)
        out[f"{v}_rmse"] = round(float(np.sqrt(ss_res / len(truth))), 2)
        recon_scores.append(out[f"{v}_recon"])

        hot = truth >= np.quantile(truth, HOTSPOT_Q)
        caught = (nearest[hot] <= sense_r).mean() if hot.any() else 0.0
        out[f"{v}_hotspot"] = round(100.0 * float(caught), 1)
        hotspot_scores.append(out[f"{v}_hotspot"])

    # --- spatial coverage (geometry only) ---------------------------------
    out["coverage"] = round(100.0 * float((nearest <= cover_r).mean()), 1)
    out["blindspot_m"] = round(float(nearest.max()), 0)

    # --- equity: population-weighted coverage gap -------------------------
    vuln = hexes.loc[land, "vulnerability"].to_numpy()
    pop = hexes.loc[land, "population"].to_numpy()
    covered = (nearest <= cover_r).astype(float)
    hi = vuln >= np.median(vuln)
    lo = ~hi

    def _wcov(mask):
        wsum = pop[mask].sum()
        return float((covered[mask] * pop[mask]).sum() / wsum) if wsum > 0 else 0.0

    # population-weighted coverage: share of *people* (not land) within range
    out["pop_coverage"] = round(100.0 * float((covered * pop).sum()
                                              / (pop.sum() + 1e-9)), 1)
    gap = (_wcov(lo) - _wcov(hi)) * 100.0          # +ve => vulnerable underserved
    out["equity_gap"] = round(gap, 1)

    # --- blended headline score -------------------------------------------
    recon = float(np.mean(recon_scores))
    hotspot = float(np.mean(hotspot_scores))
    equity_term = 100.0 - min(abs(gap), 100.0)
    out["overall"] = round(0.40 * recon + 0.30 * hotspot
                           + 0.20 * out["coverage"] + 0.10 * equity_term, 1)
    return out


def hotspot_mask(scenario, variable):
    """Boolean mask (over land hexes) of the top-decile hotspots for a field."""
    land = scenario["land_ids"]
    truth = scenario["hexes"].loc[land, variable].to_numpy()
    return land[truth >= np.quantile(truth, HOTSPOT_Q)]
