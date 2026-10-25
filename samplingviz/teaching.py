"""Classroom text: method explainers, a qualitative-methods overview, a note on
the stratified / "penetration" relabel, how scoring works, and a facilitation
run-of-show. Kept as plain markdown strings so the app stays presentation-ready
and you can edit copy without touching the logic.
"""

METHOD_EXPLAINERS = {
    "random": """
**Simple random sampling** *(probability)* — every land hex has an equal
chance of getting a sensor.

- **Strength:** unbiased; supports honest statistical inference and confidence
  intervals.
- **Weakness:** placements clump by luck, so coverage is uneven and small
  budgets can miss whole districts.
- **Watch for:** high variance between runs — hit *New scenario* / reshuffle
  and see the score bounce around.
""",
    "systematic": """
**Systematic sampling** *(probability)* — walk a fixed path across the city and
drop a sensor every *k*-th hex.

- **Strength:** near-perfect even spatial coverage; dead simple to deploy and
  explain.
- **Weakness:** can **alias** with periodic structure — line the interval up
  with the freeway grid and you either chase it or miss it entirely.
- **Watch for:** best reconstruction scores on smooth fields (heat).
""",
    "stratified": """
**Stratified sampling** *(probability)* — split the city into strata (here,
land-use types), then sample **within** each one (proportional allocation).

- **Strength:** guarantees every land use is represented; great for comparing
  groups and for catching land-use-driven hotspots (industry!).
- **Weakness:** you need to know your strata up front, and proportional
  allocation can under-sample small-but-important strata (one freeway hex).
- **This is the "penetration into strata" design** in your taxonomy — rename in
  `sampling.py` if your course uses a different label.
""",
    "clustered": """
**Cluster sampling** *(probability)* — randomly pick a few neighbourhoods and
saturate each with contiguous sensors.

- **Strength:** cheap to install and service (crews stay in one area); captures
  fine local gradients.
- **Weakness:** huge blind spots; readings inside a cluster are correlated, so
  effective sample size is far below the sensor count.
- **Watch for:** low coverage and poor reconstruction despite spending the full
  budget.
""",
    "snowball": """
**Snowball sampling** *(non-probability)* — start from one contact/tip and
recruit the neighbours of hexes you already have.

- **Strength:** the only practical option when the frame is hidden or access is
  by referral (hard-to-reach populations, informal sources, a community tip).
- **Weakness:** strongly biased toward the seed; no basis for generalisation.
  Here it seeds on a PM hotspot and then starves the rest of the map.
- **Watch for:** decent *local* hotspot recall but terrible city-wide coverage
  and equity.
""",
}

QUALITATIVE_OVERVIEW = """
### A 2-minute tour of qualitative methods

Everything above is **quantitative** — numbers on a grid. Qualitative work asks
*why*, *how*, and *for whom*, and it's what tells you where the grid is lying.

- **Interviews / key-informant interviews** — sit down with residents, plant
  operators, city staff. Surfaces sources and exposures a sensor never sees
  (idling trucks at 5am, a shift change, wood-burning in winter).
- **Focus groups** — group discussion to surface shared concerns and language;
  good for prioritising *which* variable a community even cares about.
- **Participant observation / field notes** — spend time in the place; notice
  what the data misses.
- **Document & archival analysis** — zoning maps, permits, enforcement records,
  historical redlining maps (hello, vulnerability layer).
- **Community / participatory mapping** — residents draw the map; often where
  snowball sampling actually comes from.

**Rigor words to pair with the quantitative ones:** *credibility* (vs internal
validity), *transferability* (vs external validity), *dependability* (vs
reliability), *triangulation* (combining methods so each covers the others'
blind spots). The honest monitoring network is designed with **both**.
"""

SCORING_HELP = """
Each placement is scored on four things a real network designer weighs:

| Metric | Question it answers | Good score |
|---|---|---|
| **Reconstruction** (PM2.5 / Heat / Noise R²) | If we interpolate the readings across the city, how close is the estimate to the true field? (R² → 0-100) | high |
| **Hotspot recall** | Of the worst 10% of hexes, how many sit within one hex of a sensor? | high |
| **Area cov%** | What share of the city's *land* is within ~2 hexes of a sensor? | high |
| **People cov%** | What share of the *population* is within range — do sensors cover where people actually live? | high |
| **Equity gap** | Population-weighted coverage of high-vulnerability minus low-vulnerability areas. **+** = vulnerable areas under-monitored. | near **0** |

**Overall** = 40% reconstruction + 30% hotspot + 20% area coverage + 10% equity.
Reconstruction and hotspot recall are computed per variable (PM2.5, heat,
noise) because a network tuned for one can be poor for another — that tradeoff
is the whole point.

**Tip:** use the sidebar's *"Colour the map by"* control to view **Population
density** and the **Vulnerability / EJ** layer, then see which networks leave
vulnerable, high-population areas unmonitored.
"""

RELABEL_NOTE = """
Your brief listed *snowball, random/penetration, systematic, clustered*. This
tool maps that to the classic probability designs **random · systematic ·
stratified · clustered** plus the non-probability **snowball**. The
**stratified** button is the "penetration into strata" idea — if your course
uses a different name, change `METHOD_LABELS` in `samplingviz/sampling.py`.
"""

FACILITATION = """
### Suggested 50-minute run-of-show

1. **(5 min) Cold open.** Project the map, pick *Coastal Port*, show the PM2.5
   field. Ask: *"You have budget for 8 sensors. Where do they go?"* Let the room
   argue before anyone touches it.
2. **(10 min) You place them.** Students (or groups on their own laptops) click
   to place sensors under budget. Record their *Overall* score.
3. **(10 min) Reveal the algorithms.** Auto-place each design at the same
   budget. Compare the scoreboard row by row. Who beat *systematic*? Did anyone
   accidentally do *clustered*?
4. **(10 min) Break the methods.** Switch to *Grid + Freeway* and watch
   systematic alias with the interstates. Switch to *Valley Basin* and watch the
   inversion make **everywhere** bad — now hotspot recall matters less and
   equity matters more.
5. **(10 min) Change the question.** Flip the display to *Urban heat*, then
   *Noise*. The same sensors score differently — a PM-optimal network is a poor
   heat network. Introduce multi-objective tradeoffs.
6. **(5 min) Qualitative turn.** Open the qualitative panel. *"What would an
   interview or a community map tell you that this grid can't?"* Tie snowball
   sampling back to community referral.

**Knobs for discussion:** budget (equity under scarcity), seed/New scenario
(sampling variance), vulnerability layer (environmental justice), wind +
inversion (why dispersion, not just emissions, drives exposure).
"""
