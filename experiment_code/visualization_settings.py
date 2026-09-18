"""Shared visualization settings for all experiments."""

from collections import deque

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib import patheffects as pe
from matplotlib.colors import LinearSegmentedColormap

plt.rcParams.update({"font.family": "serif", "mathtext.fontset": "cm",
                     "font.size": 14, "savefig.dpi": 300})

# Colors

PALETTE = [
    "#1560bd",
    "#8db600",
    "#ffb7c5",
    "#ffa812",
    "#006b3c",
    "#69359c",
    "#d11a42",
    "#56b4e9",
    "#000000",
    "#999999"]

GRID_COLOR = "#eae8e0"
SECONDARY = "#333333"
PRIMARY_INK = "#0b0b0b"

# Colors for the decades on the metric vs 
YEAR_COLORS = {
    1980: "#03336e",
    # 1990: "#006b3c",
    # 2000: "#8db600",
    # 2010: "#ffa812",
    # 2020: "#d11a42",
    1990: "#0d4aa7",
    2000: "#3374d9",
    2010: "#5d9bf8",
    2020: "#85b5f7",
    # 2020: "#d6e8ff",
    }

# Two main metric colors (mainly for observed diffusion figures)
BLUE = "#1560bd" # Capy
ORANGE = "#ffa812" # Moran's I
# GREEN = "#69359c"
TANGERINE = "#ed5113"
# SKY = "#56b4e9"
CAPY = BLUE
MORAN = ORANGE

# Metrics

GRID_METRICS = {
    "moran_P": "Moran's I",
    "dissimilarity_1": "Dissimilarity",
    "half_edge_1": "Capy",
}


def _build_metric_labels() -> dict:
    """Map metric keys to (title, subtitle) pairs for plot labels.

    Subtitles describe parameter values such as:
        Lambda (λ) values for Capy, i.e. weights on the within units vs. between units terms in the Half Edge formula.
        Exact-count or asymptotic variants for Capy.
        Moran matrix variants: A for adjacency, P for adjacency normalized, L for Laplacian, M for Metropolis, D_1 inverse distance, and D_2 for inverse distance squared.
    """
    lam_display = {"0": r"$\lambda=0$", "0.5": r"$\lambda=0.5$", "1": r"$\lambda=1$", "2": r"$\lambda=2$", "10": r"$\lambda=10$", "lim": r"$\lambda=\infty$"}
    bases = {
        "skew_self": "Skew (self)",
        "skew_other": "Skew (other)",
        "edge": "Edge",
        "skew'_self": "Skew′ (self)",
        "skew'_other": "Skew′ (other)",
        "half_edge": "Half Edge"}
    labels = {}
    for lam, lam_label in lam_display.items():
        for base, title in bases.items():
            labels[f"{base}_{lam}"] = (title, lam_label)
            labels[f"{base}_exact_{lam}"] = (title, f"Exact counts; {lam_label}")
    _dissim_labels = {1: r"$L_1$ norm (standard)", 2: r"$L_2$ norm", 10: r"$L_{10}$ norm"}
    for p in [1, 2, 10]:
        labels[f"dissimilarity_{p}"] = ("Dissimilarity", _dissim_labels[p])
    labels.update({
        "e_assort": ("Assortativity", "Edge"),
        "he_assort": ("Assortativity", "Half-edge"),
        "gini": ("Gini Coefficient", ""),
    })
    for suffix, subtitle in [
        ("A", "Adjacency"), ("P", "Adjacency normalized (P-matrix)"),
        ("L", "Laplacian"), ("M", "Metropolis (M-matrix)"),
        ("D_1", "Inverse distance"), ("D_2", "Inverse distance squared"),
    ]:
        labels[f"moran_{suffix}"] = ("Moran's I", subtitle)
        labels[f"moran_{suffix}_white"] = ("Moran's I (White)", subtitle)
    return labels


METRIC_LABELS = _build_metric_labels()

METRICS = [
    "e_assort", "he_assort",
    "skew_self_0", "skew_other_0", "edge_0",
    "skew'_self_0", "skew'_other_0", "half_edge_0",
    "skew_self_exact_0", "skew_other_exact_0", "edge_exact_0",
    "skew'_self_exact_0", "skew'_other_exact_0", "half_edge_exact_0",
    "skew_self_0.5", "skew_other_0.5", "edge_0.5",
    "skew'_self_0.5", "skew'_other_0.5", "half_edge_0.5",
    "skew_self_exact_0.5", "skew_other_exact_0.5", "edge_exact_0.5",
    "skew'_self_exact_0.5", "skew'_other_exact_0.5", "half_edge_exact_0.5",
    "skew_self_1", "skew_other_1", "edge_1",
    "skew'_self_1", "skew'_other_1", "half_edge_1",
    "skew_self_exact_1", "skew_other_exact_1", "edge_exact_1",
    "skew'_self_exact_1", "skew'_other_exact_1", "half_edge_exact_1",
    "skew_self_2", "skew_other_2", "edge_2",
    "skew'_self_2", "skew'_other_2", "half_edge_2",
    "skew_self_exact_2", "skew_other_exact_2", "edge_exact_2",
    "skew'_self_exact_2", "skew'_other_exact_2", "half_edge_exact_2",
    "skew_self_10", "skew_other_10", "edge_10",
    "skew'_self_10", "skew'_other_10", "half_edge_10",
    "skew_self_exact_10", "skew_other_exact_10", "edge_exact_10",
    "skew'_self_exact_10", "skew'_other_exact_10", "half_edge_exact_10",
    "skew_self_lim", "skew_other_lim", "edge_lim",
    "skew'_self_lim", "skew'_other_lim", "half_edge_lim",
    "skew_self_exact_lim", "skew_other_exact_lim", "edge_exact_lim",
    "skew'_self_exact_lim", "skew'_other_exact_lim", "half_edge_exact_lim",
    "dissimilarity_1", "dissimilarity_2", "dissimilarity_10",
    "gini",
    "moran_A", "moran_P", "moran_L", "moran_M", "moran_D_1", "moran_D_2",
]

# Helper functions

def _short_name(cbsa_title: str) -> str:
    city_part, sep, state = cbsa_title.rpartition(", ")
    return f"{city_part.split('-')[0]}, {state}" if sep else cbsa_title


def _shorten_prefix(prefix: str) -> str:
    return (
        prefix
        .replace("white_black", "wb")
        .replace("white_poc", "wpoc")
        .replace("block_groups", "bg"))


def _apply_panel_style(ax, years: list, ylim: tuple, y_range: float = float("inf")) -> None:
    """Apply shared styling to baseline metric-over-time panels.

    Called by `baseline/visualization/line_plots` functions: `plot_family_grids()`, `plot_grid_all_census_areas()`,
    `plot_grid_top10()`, and by `main()` in `generate_figures.py`, all under `experiment_code/baseline/visualization/line_plots/`.

    Sets square axes, a background grid, hidden spines, year ticks, and
    one-decimal y-axis labels; applies y-limits when ylim is provided.
    """
    ax.set_box_aspect(1)
    ax.set_axisbelow(True)
    ax.grid(color=GRID_COLOR, linewidth=0.8)
    ax.spines[["top", "right", "left", "bottom"]].set_visible(False)
    ax.tick_params(length=0, labelsize=plt.rcParams['font.size'],
                   labelcolor=SECONDARY)
    ax.tick_params(axis="x", length=0, labelsize=plt.rcParams['font.size'], 
                   labelcolor=SECONDARY, pad=15)
    # ax.tick_params(axis="y", length=0, labelsize=plt.rcParams['font.size'], 
                #    labelcolor=SECONDARY)
    ax.set_xticks(years)
    ax.set_xticklabels([str(y) for y in years], fontsize=plt.rcParams['font.size'])
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.1f"))
    ax.yaxis.set_major_locator(mticker.MaxNLocator(nbins=4))
    if ylim is not None:
        ax.set_ylim(*ylim)


# Radial plot helpers

RADIAL_SURFACE = "#fcfcfb"
RADIAL_BASELINE = "#c3c2b7" 
BLUE_RAMP = [
    "#d6e8ff", "#c2dcfe", "#aaccfd", "#90bbfb", "#76a9f7", "#5e97f0",
    "#4685e6", "#3374d9", "#2567cc", "#1d62c2", "#1a61be", "#1560bd"]
CMAP_BLACK_SHARE = LinearSegmentedColormap.from_list("black_share", BLUE_RAMP)
DOT_SIZE = 20
DOT_RING = 0.2


def _centroid(G, n):
    return np.array([G.nodes[n]["centroid_x"], G.nodes[n]["centroid_y"]])


def bfs(G, medoid):
    """Edge distance from medoid to every reachable node."""
    assert medoid in G, f"medoid {medoid} not in graph"
    d = {medoid: 0}
    Q = deque([medoid])
    while Q:
        u = Q.popleft()
        for v in G[u]:
            if v not in d:
                d[v] = d[u] + 1
                Q.append(v)
    return d


def bearings(G, medoid, nodes):
    """Angle bearing of each tract's centroid from the medoid, in radians."""
    centroid = _centroid(G, medoid)
    out_coords = {}
    for n in nodes:
        v = _centroid(G, n) - centroid
        out_coords[n] = float(np.arctan2(v[1], v[0]))
    return out_coords


def radial_coords(d, angle, nodes):
    """(x, y) = (r cos theta, r sin theta) for each node."""
    return {n: (d[n] * np.cos(angle[n]), d[n] * np.sin(angle[n])) for n in nodes}


def panel_radial(ax, coords, share, rmax, reach, title, label_rings=(5, 10)):
    """Radial plots panel. r = edge-distance from medoid; color = Black share."""
    for r in range(1, rmax + 1):
        ax.add_patch(plt.Circle((0, 0), r, fill=False, ec=GRID_COLOR, lw=0.7, zorder=0))
    ax.add_patch(plt.Circle((0, 0), reach, fill=False, ec=RADIAL_BASELINE, lw=1.1,
                             ls=(0, (4, 3)), zorder=1))
    marks = [r for r in label_rings if r <= reach - 2] + [reach]
    if rmax >= reach + 2:
        marks.append(rmax)
    for r in marks:
        ax.text(-r * 0.7071, r * 0.7071, str(r), fontsize=plt.rcParams['font.size']-2,
                color=SECONDARY, ha="center", va="center", zorder=7,
                path_effects=[pe.withStroke(linewidth=2.6, foreground=RADIAL_SURFACE)])
    xy = np.array([coords[n] for n in coords])
    c = np.array([share[n]  for n in coords])
    sc = ax.scatter(xy[:, 0], xy[:, 1], c=c, cmap=CMAP_BLACK_SHARE, vmin=0.0, vmax=1.0,
                    s=DOT_SIZE, lw=DOT_RING, edgecolors=RADIAL_SURFACE, alpha=1, zorder=3)
    ax.plot(0, 0, "*", ms=13, mfc=TANGERINE, mec=RADIAL_SURFACE, mew=0.8, zorder=5)
    lim = rmax + 0.8
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(title, fontsize=plt.rcParams['font.size'],
                  loc='center')
    return sc
