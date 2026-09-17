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
_BLUE_RAMP    = [
    "#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5",
    "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b",
]
_CMAP_SHARE   = LinearSegmentedColormap.from_list("black_share", _BLUE_RAMP)
_DOT_SIZE     = 26
_DOT_RING     = 0.8


# ── graph ─────────────────────────────────────────────────────────────────────

def centroid(G, n):
    return np.array([G.nodes[n]["centroid_x"], G.nodes[n]["centroid_y"]])


# ── distance ──────────────────────────────────────────────────────────────────

def bfs(G, root):
    """Hop distance from `root` to every reachable node."""
    assert root in G, f"root {root} not in graph"
    d = {root: 0}
    Q = deque([root])
    while Q:
        u = Q.popleft()
        for v in G[u]:
            if v not in d:
                d[v] = d[u] + 1
                Q.append(v)
    return d


# ── radial ────────────────────────────────────────────────────────────────────

def bearings(G, root, nodes):
    """Compass bearing of each tract's centroid from the root, in radians."""
    o = centroid(G, root)
    out = {}
    for n in nodes:
        v = centroid(G, n) - o
        out[n] = float(np.arctan2(v[1], v[0]))
    return out


def radial_coords(d, angle, nodes):
    """(x, y) = (r cos theta, r sin theta) for each node."""
    return {n: (d[n] * np.cos(angle[n]), d[n] * np.sin(angle[n])) for n in nodes}


# ── figures ───────────────────────────────────────────────────────────────────

def panel_radial(ax, coords, share, rmax, reach, title, label_rings=(5, 10)):
    """Radial collapse panel.  r = edge-distance from medoid; colour = Black share."""
    for r in range(1, rmax + 1):
        ax.add_patch(plt.Circle((0, 0), r, fill=False, ec=_GRIDLINE, lw=0.7, zorder=0))
    ax.add_patch(plt.Circle((0, 0), reach, fill=False, ec=_BASELINE, lw=1.1,
                             ls=(0, (4, 3)), zorder=1))
    marks = [r for r in label_rings if r <= reach - 2] + [reach]
    if rmax >= reach + 2:
        marks.append(rmax)
    for r in marks:
        ax.text(-r * 0.7071, r * 0.7071, str(r), fontsize=7.5,
                color=_INK_SECONDARY, ha="center", va="center", zorder=7,
                path_effects=[pe.withStroke(linewidth=2.6, foreground=_SURFACE)])

    xy = np.array([coords[n] for n in coords])
    c  = np.array([share[n]  for n in coords])
    sc = ax.scatter(xy[:, 0], xy[:, 1], c=c, cmap=_CMAP_SHARE, vmin=0.0, vmax=1.0,
                    s=_DOT_SIZE, lw=_DOT_RING, edgecolors=_SURFACE, alpha=1, zorder=3)
    ax.plot(0, 0, "*", ms=13, mfc="#eb6834", mec=_SURFACE, mew=0.8, zorder=5)
    lim = rmax + 0.8
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(title, fontsize=10, loc='center')
    return sc
