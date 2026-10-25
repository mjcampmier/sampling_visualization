"""The five sampling designs.

Every function takes a scenario, a sensor count ``n`` and a seeded ``rng`` and
returns a list of hex indices (restricted to land — you can't drop a monitor
in the bay). They are written so the *behaviour* contrasts are obvious to
students:

* ``simple_random``  — probability sample, uniform over land. Unbiased but
                       lumpy; coverage depends on luck.
* ``systematic``     — every k-th hex along a serpentine path. Beautifully even
                       coverage; can alias with periodic structure (e.g. a grid
                       of freeways).
* ``stratified``     — proportional allocation across land-use strata, random
                       within. Guarantees every land-use type is represented.
                       (This is the "penetration into strata" design; relabel
                       freely for your course.)
* ``clustered``      — a few randomly chosen neighbourhoods, sensors packed into
                       contiguous blocks. Cheap to service, lots of blind spots.
* ``snowball``       — start from one contact/tip and recruit neighbours of
                       already-chosen hexes. Connected, strongly biased toward
                       the seed — the classic non-probability cautionary tale.

``METHODS`` lists them in teaching order with display colours.
"""

from __future__ import annotations

import numpy as np

METHODS = [
    ("random",     "Simple random", "#1f78b4"),
    ("systematic", "Systematic",    "#33a02c"),
    ("stratified", "Stratified",    "#ff7f00"),
    ("clustered",  "Clustered",     "#e31a1c"),
    ("snowball",   "Snowball",      "#6a3d9a"),
]
METHOD_LABELS = {k: lbl for k, lbl, _ in METHODS}
METHOD_COLORS = {k: c for k, _, c in METHODS}


def _serpentine_order(hexes, land_ids):
    """Order land hexes along a boustrophedon path (left-right, then flip)."""
    sub = hexes.loc[land_ids, ["row", "col"]].copy()
    # reverse column direction on odd rows so the path snakes continuously
    sub["key_col"] = np.where(sub["row"] % 2 == 0, sub["col"], -sub["col"])
    sub = sub.sort_values(["row", "key_col"])
    return sub.index.to_numpy()


def simple_random(scenario, n, rng):
    land = scenario["land_ids"]
    n = min(n, len(land))
    return rng.choice(land, size=n, replace=False).tolist()


def systematic(scenario, n, rng):
    land = scenario["land_ids"]
    order = _serpentine_order(scenario["hexes"], land)
    n = min(n, len(order))
    if n == 0:
        return []
    step = len(order) / n
    start = rng.integers(0, max(1, int(step)))
    picks = [order[min(len(order) - 1, int(start + k * step))] for k in range(n)]
    # de-dup while keeping count close to n
    seen, out = set(), []
    for p in picks:
        if p not in seen:
            seen.add(p)
            out.append(int(p))
    return out


def stratified(scenario, n, rng):
    """Proportional allocation across land-use strata, random within."""
    hexes = scenario["hexes"]
    land = scenario["land_ids"]
    n = min(n, len(land))
    groups = hexes.loc[land].groupby("land_use").groups  # label -> index
    labels = list(groups)
    sizes = np.array([len(groups[l]) for l in labels], dtype=float)
    # largest-remainder apportionment so allocations sum to exactly n
    exact = sizes / sizes.sum() * n
    alloc = np.floor(exact).astype(int)
    remainder = n - alloc.sum()
    for i in np.argsort(-(exact - alloc))[:remainder]:
        alloc[i] += 1

    out = []
    for label, k in zip(labels, alloc):
        members = np.asarray(groups[label])
        k = min(k, len(members))
        if k > 0:
            out.extend(rng.choice(members, size=k, replace=False).tolist())
    return [int(i) for i in out]


def _grow_region(seeds, size, neighbors, allowed, rng):
    """BFS-grow a contiguous region of `size` hexes from the given seeds."""
    allowed = set(int(a) for a in allowed)
    chosen, frontier = set(), list(seeds)
    rng.shuffle(frontier)
    while frontier and len(chosen) < size:
        cur = frontier.pop(0)
        if cur in chosen or cur not in allowed:
            continue
        chosen.add(cur)
        nbs = [j for j in neighbors[cur] if j in allowed and j not in chosen]
        rng.shuffle(nbs)
        frontier.extend(nbs)
    return chosen


def clustered(scenario, n, rng, cluster_size=4):
    """A handful of neighbourhoods, sensors packed into contiguous blocks."""
    land = scenario["land_ids"]
    n = min(n, len(land))
    if n == 0:
        return []
    n_clusters = max(1, round(n / cluster_size))
    centers = rng.choice(land, size=min(n_clusters, len(land)), replace=False)
    per = int(np.ceil(n / len(centers)))
    chosen = set()
    for c in centers:
        region = _grow_region([int(c)], per, scenario["neighbors"], land, rng)
        chosen |= region
        if len(chosen) >= n:
            break
    chosen = list(chosen)[:n]
    # top up randomly if BFS fell short (e.g. small land islands)
    if len(chosen) < n:
        extra = [i for i in land if i not in set(chosen)]
        rng.shuffle(extra)
        chosen.extend(extra[: n - len(chosen)])
    return [int(i) for i in chosen]


def snowball(scenario, n, rng, seed_hex=None):
    """Referral growth: recruit neighbours of already-sampled hexes.

    Seeds on a high-PM hex (a "tip") by default, so the bias is pedagogically
    visible: the network grows outward from one spot and starves the rest of
    the map.
    """
    hexes = scenario["hexes"]
    land = set(int(i) for i in scenario["land_ids"])
    n = min(n, len(land))
    if n == 0:
        return []
    neighbors = scenario["neighbors"]

    if seed_hex is None:
        land_arr = scenario["land_ids"]
        pm = hexes.loc[land_arr, "PM25"].to_numpy()
        top = land_arr[pm >= np.quantile(pm, 0.85)]
        seed_hex = int(rng.choice(top))

    chosen = {seed_hex}
    while len(chosen) < n:
        # candidates = land neighbours of the current set, not yet chosen
        cand = {}
        for h in chosen:
            for j in neighbors[h]:
                if j in land and j not in chosen:
                    cand[j] = cand.get(j, 0) + 1  # weight by # of referrals
        if not cand:
            break
        ids = np.array(list(cand))
        weights = np.array(list(cand.values()), dtype=float)
        weights = weights / weights.sum()
        chosen.add(int(rng.choice(ids, p=weights)))
    return [int(i) for i in chosen]


def place(method, scenario, n, seed):
    """Dispatch to a design with a reproducible, method-specific rng."""
    rng = np.random.default_rng(hash((scenario["seed"], method, n, seed)) % (2**32))
    if method == "random":
        return simple_random(scenario, n, rng)
    if method == "systematic":
        return systematic(scenario, n, rng)
    if method == "stratified":
        return stratified(scenario, n, rng)
    if method == "clustered":
        return clustered(scenario, n, rng)
    if method == "snowball":
        return snowball(scenario, n, rng)
    raise ValueError(f"unknown method: {method}")
