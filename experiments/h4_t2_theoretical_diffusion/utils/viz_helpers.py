"""Helpers for radial visualisation — extracted from archive/h4_t3_observed_edge_diffusion/utils."""

from collections import deque

import numpy as np
import matplotlib.pyplot as plt
from matplotlib import patheffects as pe
from matplotlib.colors import LinearSegmentedColormap

# ── style constants used by panel_radial ─────────────────────────────────────
_SURFACE      = "#fcfcfb"
_INK_SECONDARY = "#52514e"
_GRIDLINE     = "#e1e0d9"
_BASELINE     = "#c3c2b7"

PALETTE = [
    "#8db600",
    "#1560bd",
    "#ffb7c5",
    "#ffa812",
    "#006b3c",
    "#69359c",
    "#d11a42",
    "#56b4e9",  # sky
    "#000000",  # black
    "#999999",  # gray
]

RED = "#d11a42"
BLUE = "#006b3c"# "#2267bc"
ORANGE = "#ffa812"

GRID_METRICS = {
    "moran_P": "Moran's I",
    "dissimilarity_1": "Dissimilarity",
    "half_edge_1": "Capy",
}