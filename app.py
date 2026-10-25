"""Sensor Placement Lab — an interactive classroom tool.

Run with:   streamlit run app.py

Students dice a procedural city into hexes, read a land-use emissions
inventory (PM2.5 / urban heat / noise), then place air-quality sensors under a
budget — by hand and via five sampling designs — and compare how well each
network reconstructs the truth, catches hotspots, covers space, and serves
vulnerable communities.
"""

from __future__ import annotations

import warnings
# system Python 3.9 here is built against LibreSSL; silence the unrelated
# urllib3 import-time notice so the classroom console stays clean.
warnings.filterwarnings("ignore", message=r"urllib3 v2 only supports OpenSSL.*")

import numpy as np
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from samplingviz.city import PRESETS, generate_scenario
from samplingviz.sampling import METHODS, place
from samplingviz.scoring import score_placement
from samplingviz import teaching
from samplingviz.viz import build_map, display_options, nearest_land_hex
from samplingviz.sampling import METHOD_COLORS, METHOD_LABELS

COST_PER_SENSOR = 1000  # dollars per multi-parameter low-cost node

st.set_page_config(page_title="Sensor Placement Lab", page_icon="📡",
                   layout="wide")


@st.cache_data(show_spinner=False)
def _scenario(preset_key, seed):
    return generate_scenario(preset_key, seed)


# --- session bootstrap ---------------------------------------------------
ss = st.session_state
ss.setdefault("seed", 42)
ss.setdefault("preset", "coastal")
ss.setdefault("student", [])
ss.setdefault("_last_click", None)
ss.setdefault("overlay", "None")


def _reshuffle():
    ss.seed = int(np.random.default_rng().integers(1, 99_999))


# --- sidebar -------------------------------------------------------------
with st.sidebar:
    st.header("🏙️ Scenario")
    preset = st.selectbox(
        "City", list(PRESETS), key="preset",
        format_func=lambda k: PRESETS[k].name,
    )
    st.caption(PRESETS[preset].blurb)
    st.button("🎲 New scenario (reshuffle)", on_click=_reshuffle,
              use_container_width=True)
    seed = st.number_input("Seed", 1, 999_999, key="seed",
                           help="Same seed = same city. Give each group a seed.")

    st.header("💰 Budget")
    budget = st.slider("Monitoring budget ($)", 2_000, 40_000, 15_000,
                       step=COST_PER_SENSOR)
    n_sensors = budget // COST_PER_SENSOR
    st.metric("Sensors you can buy", n_sensors,
              help=f"${COST_PER_SENSOR:,} per multi-parameter node")

    st.header("🗺️ Display")
    opts = display_options()
    display_var = st.selectbox("Colour the map by", list(opts),
                               format_func=lambda k: opts[k])
    show_hotspots = st.checkbox("Outline hotspots (worst 10%)", value=True)
    basemap = st.checkbox("Show street basemap", value=True)
    st.caption("Land use is stylised; geography is illustrative "
               "(real city centre for scale).")

# rebuild + clear placements when the city or seed changes
sig = (preset, int(seed))
if ss.get("_sig") != sig:
    ss._sig = sig
    ss.student = []
    ss._last_click = None

sc = _scenario(preset, int(seed))

# --- header --------------------------------------------------------------
st.title("📡 Sensor Placement Lab")
st.markdown(
    f"**{PRESETS[preset].name}** · seed `{seed}` · budget **{n_sensors} "
    f"sensors** — click hexes to place *your* network, then compare it to the "
    f"sampling designs on the right."
)

map_col, score_col = st.columns([1.5, 1], gap="large")

# --- map column ----------------------------------------------------------
with map_col:
    overlay_choice = st.radio(
        "Overlay an algorithm's placement on the map",
        ["None"] + [lbl for _, lbl, _ in METHODS],
        horizontal=True, key="overlay",
    )
    overlay_ids, overlay_color, overlay_label = [], "#6a3d9a", "method"
    if overlay_choice != "None":
        mkey = {lbl: k for k, lbl, _ in METHODS}[overlay_choice]
        overlay_ids = place(mkey, sc, n_sensors, int(seed))
        overlay_color = METHOD_COLORS[mkey]
        overlay_label = overlay_choice

    fmap = build_map(sc, display_var, ss.student, overlay_ids=overlay_ids,
                     overlay_color=overlay_color, overlay_label=overlay_label,
                     show_hotspots=show_hotspots, basemap=basemap)
    state = st_folium(fmap, height=560, use_container_width=True, key="map",
                      returned_objects=["last_clicked"])

    placed = len(ss.student)
    cols = st.columns(3)
    cols[0].metric("Placed", f"{placed}/{n_sensors}")
    cols[1].metric("Remaining", max(0, n_sensors - placed))
    if cols[2].button("🧹 Clear my sensors", use_container_width=True):
        ss.student = []
        ss._last_click = None
        st.rerun()
    st.caption("Click an empty hex to add a sensor · click one of your sensors "
               "to remove it · you can't place over water.")

    # handle a fresh click
    click = state.get("last_clicked") if state else None
    if click and click != ss._last_click:
        ss._last_click = click
        hx = nearest_land_hex(sc, click["lat"], click["lng"])
        if hx is not None:
            if hx in ss.student:
                ss.student = [i for i in ss.student if i != hx]
                st.rerun()
            elif placed < n_sensors:
                ss.student = ss.student + [hx]
                st.rerun()
            else:
                st.toast(f"Budget reached ({n_sensors} sensors). "
                         "Remove one or raise the budget.", icon="⚠️")

# --- scoreboard column ---------------------------------------------------
with score_col:
    st.subheader("🏆 Scoreboard")
    st.caption("Higher is better, except **Equity gap** (aim for 0). Scores "
               "cover all three variables at once.")

    networks = {"You": list(ss.student)}
    for key, label, _ in METHODS:
        networks[label] = place(key, sc, n_sensors, int(seed))

    rows = []
    for name, ids in networks.items():
        s = score_placement(sc, ids)
        hotspot = np.mean([s["PM25_hotspot"], s["heat_hotspot"],
                           s["noise_hotspot"]])
        rows.append({
            "Network": name,
            "Overall": s["overall"],
            "PM2.5 R²": s["PM25_recon"],
            "Heat R²": s["heat_recon"],
            "Noise R²": s["noise_recon"],
            "Hotspot%": round(float(hotspot), 1),
            "Area cov%": s["coverage"],
            "People cov%": s["pop_coverage"],
            "Equity gap": s["equity_gap"],
            "Sensors": s["n_sensors"],
        })
    df = pd.DataFrame(rows).set_index("Network")

    good_cols = ["Overall", "PM2.5 R²", "Heat R²", "Noise R²",
                 "Hotspot%", "Area cov%", "People cov%"]
    sty = (df.style
           .format("{:.1f}", subset=good_cols + ["Equity gap"])
           .format("{:.0f}", subset=["Sensors"])
           .highlight_max(subset=["Overall"], color="#b7e4c7")
           .set_properties(**{"font-weight": "bold"}, subset=pd.IndexSlice[["You"], :]))
    st.dataframe(sty, width="stretch")

    you = df.loc["You", "Overall"]
    best_algo = df.drop(index="You")["Overall"].idxmax()
    best_algo_score = df.loc[best_algo, "Overall"]
    if len(ss.student) == 0:
        st.info("Place some sensors to get on the board. The best algorithm "
                f"so far is **{best_algo}** at **{best_algo_score:.0f}**.")
    elif you >= best_algo_score:
        st.success(f"You ({you:.0f}) are beating every algorithm — "
                   f"best was **{best_algo}** at {best_algo_score:.0f}. "
                   "What design did you intuitively use?")
    else:
        st.warning(f"You: **{you:.0f}**. Best algorithm: **{best_algo}** at "
                   f"**{best_algo_score:.0f}**. Try the overlay to see where "
                   "it put sensors.")

    st.caption(teaching.RELABEL_NOTE)

# --- scoring reference ---------------------------------------------------
st.divider()
with st.expander("📏 How placements are scored", expanded=False):
    st.markdown(teaching.SCORING_HELP)
