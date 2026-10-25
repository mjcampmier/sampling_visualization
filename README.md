# 📡 Sensor Placement Lab

An **interactive classroom tool** for teaching sampling design through
environmental sensor placement. A procedural city is diced into hexagons; a
land-use **emissions inventory** produces realistic **PM2.5**, **urban-heat**,
and **noise** fields; students place air-quality sensors under a **budget** —
by hand *and* via five sampling designs — then compare how well each network
reconstructs the truth, catches hotspots, covers space, and serves vulnerable
communities.

Built for a unit introducing **probability and non-probability sampling**
(simple random, systematic, stratified, clustered, snowball) with a short
**qualitative-methods** coda.

---

## Quick start

```bash
# from the project root, using the existing .venv
uv pip install -r requirements.txt        # or: pip install -r requirements.txt
streamlit run app.py                       # opens http://localhost:8501
```

In PyCharm you can also just press **Run** on `main.py` — it shells out to
`streamlit run app.py`.

> The app is fully offline/procedural. The **only** thing that needs internet is
> the optional street basemap (OpenStreetMap tiles). Turn off *"Show street
> basemap"* in the sidebar for a self-contained, tile-free view.

---

## What students see

- **A hex map of a city** coloured by the variable on display (PM2.5, heat,
  noise, population, vulnerability, or land-use category). Hover any hex for all
  its values.
- **A budget** → a number of sensors they can afford (\$1,000 each).
- **Click to place** their own sensors (click again to remove); **overlay** any
  algorithm's placement to compare.
- **A scoreboard** ranking *You* against all five designs on Overall score,
  per-variable reconstruction (R²), hotspot recall, coverage, and an
  environmental-justice **equity gap**.
- **Teaching panels**: method explainers, a qualitative-methods overview, how
  scoring works, and a facilitation run-of-show.

### The three cities (presets)
| Preset | What makes it teach | 
|---|---|
| **Coastal Port** | Bay + waterfront industry; onshore wind pushes the plume inland. Water hexes can't hold sensors. |
| **Valley Basin** | Wintertime **inversion** traps pollution over the whole bowl — hotspot recall matters less, equity more. |
| **Grid + Freeway** | A freeway interchange; watch **systematic** sampling alias with the regular road grid. |

Change the **seed** (or hit *🎲 New scenario*) to give every student/group their
own version of the same city — great for showing sampling *variance*.

---

## The sampling designs

| Design | Type | One-line takeaway |
|---|---|---|
| **Simple random** | probability | Unbiased but lumpy; coverage is luck. |
| **Systematic** | probability | Even coverage; can alias with periodic structure. |
| **Stratified** | probability | Every land-use type represented; needs a known frame. |
| **Clustered** | probability | Cheap to service, lots of blind spots. |
| **Snowball** | non-probability | Grows from one tip; strongly biased, poor coverage. |

> **Taxonomy note.** Your brief listed *snowball, random/penetration,
> systematic, clustered*. This maps "penetration" to the classic **stratified**
> design. To relabel, edit `METHODS` / `METHOD_LABELS` in
> `samplingviz/sampling.py` — nothing else depends on the label.

---

## How placements are scored

| Metric | Question | Good |
|---|---|---|
| **Reconstruction (R²)** | Interpolate the readings city-wide — how close to truth? | high |
| **Hotspot recall** | Of the worst 10% of hexes, how many are within one hex of a sensor? | high |
| **Coverage** | Share of the city within ~2 hexes of a sensor. | high |
| **Equity gap** | Pop-weighted coverage of high- minus low-vulnerability areas (**+** = vulnerable under-monitored). | ~0 |

**Overall** = 40% reconstruction + 30% hotspot + 20% coverage + 10% equity,
averaged over all three variables. Because the three fields have different
spatial structure, a network tuned for PM2.5 scores differently on heat or
noise — that tradeoff is the point.

---

## Suggested 50-minute run-of-show

1. **Cold open (5m)** — project a city, ask *"8 sensors, where do they go?"*
2. **You place them (10m)** — students place under budget; record the score.
3. **Reveal the algorithms (10m)** — overlay each design at the same budget;
   walk the scoreboard. Who beat *systematic*? Who accidentally did *clustered*?
4. **Break the methods (10m)** — *Grid + Freeway* (systematic aliasing),
   *Valley Basin* (inversion makes everywhere bad).
5. **Change the question (10m)** — switch display to heat, then noise; the same
   sensors score differently (multi-objective tradeoff).
6. **Qualitative turn (5m)** — open the qualitative panel; tie snowball sampling
   to community referral and ask what an interview/map would reveal.

The full guide is also inside the app under **Teaching panels → Facilitation
guide**.

---

## Project layout

```
app.py                 Streamlit entry point (UI, click handling, scoreboard)
main.py                PyCharm-friendly launcher -> streamlit run app.py
samplingviz/
  city.py              hex grid + procedural, seeded land use
  inventory.py         land use -> PM2.5 / heat / noise fields (dispersion, wind, inversion)
  sampling.py          the five sampling designs
  scoring.py           placement metrics (reconstruction, hotspot, coverage, equity)
  viz.py               folium map building + click-to-hex snapping
  teaching.py          classroom text (edit freely — no logic here)
```

Everything in `samplingviz/` is plain numpy/pandas and runs without Streamlit,
so you can build new scenarios or metrics from a notebook:

```python
from samplingviz.city import generate_scenario
from samplingviz.sampling import place
from samplingviz.scoring import score_placement

sc = generate_scenario("valley", seed=7)
score_placement(sc, place("systematic", sc, n=15, seed=7))
```

## Knobs worth tweaking for your course
- **Emission factors / ranges** — `samplingviz/inventory.py` (`_EMIT`, `VARIABLES`).
- **City layouts, wind, grid size** — `samplingviz/city.py` (`_land_use_drivers`, `COLS/ROWS/HEX_SIZE_M`).
- **Sensor cost / default budget** — `COST_PER_SENSOR` and the slider in `app.py`.
- **Scoring weights** — `score_placement` in `samplingviz/scoring.py`.
