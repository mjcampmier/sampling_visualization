"""samplingviz — an interactive sensor-placement teaching tool.

A procedural city is diced into hexagons, a land-use based *emissions
inventory* produces realistic PM2.5 / urban-heat / noise fields, and students
place air-quality sensors under a budget using different sampling designs
(simple random, systematic, stratified, clustered, snowball). Placements are
scored on how well they reconstruct the true field, catch hotspots, cover
space, and serve vulnerable populations.

Modules
-------
city       : hex grid + procedural, seeded land use
inventory  : land use -> PM2.5 / heat / noise fields (dispersion, wind, inversion)
sampling   : the five sampling designs
scoring    : placement metrics (reconstruction, hotspot recall, coverage, equity)
viz        : folium map building
teaching   : classroom text (method explainers, qualitative overview, facilitation)
"""

from .city import PRESETS, generate_scenario
from .inventory import VARIABLES

__all__ = ["PRESETS", "generate_scenario", "VARIABLES"]
