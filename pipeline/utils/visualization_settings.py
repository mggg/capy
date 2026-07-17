import matplotlib.ticker as mticker

PALETTE = [
    "#0072b2",  # blue
    "#e69f00",  # amber
    "#009e73",  # green
    "#cc79a7",  # mauve
    "#56b4e9",  # sky
    "#d55e00",  # vermillion
    "#c3ba32",  # yellow
    "#000000",  # black
    "#999999",  # gray
    "#44aa99",  # teal
]

GRID_METRICS = {
    "moran_P": "Moran's I (P Matrix)",
    "dissimilarity_1": "Dissimilarity",
    "half_edge_1": "Half Edge (λ=1)",
}


def _build_metric_labels() -> dict:
    lam_display = {"0": "λ=0", "0.5": "λ=0.5", "1": "λ=1", "2": "λ=2", "10": "λ=10", "lim": "λ=∞"}
    bases = {
        "skew_self":   "Skew (self)",
        "skew_other":  "Skew (other)",
        "edge":        "Edge",
        "skew'_self":  "Skew′ (self)",
        "skew'_other": "Skew′ (other)",
        "half_edge":   "Half Edge",
    }
    labels = {}
    for lam, lam_label in lam_display.items():
        for base, title in bases.items():
            labels[f"{base}_{lam}"] = (title, lam_label)
            labels[f"{base}_exact_{lam}"] = (title, f"Exact counts; {lam_label}")
    _dissim_labels = {1: "L1 norm (standard)", 2: "L2 norm", 10: "L10 norm"}
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


def _short_name(cbsa_title: str) -> str:
    city_part, _, state = cbsa_title.rpartition(", ")
    return f"{city_part.split('-')[0]}, {state}"


def _apply_panel_style(ax, years: list, ylim: tuple) -> None:
    BG_PANEL = "#ececec"
    ax.set_facecolor(BG_PANEL)
    ax.set_box_aspect(1)
    ax.grid(axis="y", color="white", linewidth=1.3, zorder=0)
    ax.spines[["top", "right", "left", "bottom"]].set_visible(False)
    ax.tick_params(length=0, labelsize=8, labelcolor="#444444")
    ax.set_xticks(years)
    ax.set_xticklabels([str(y) for y in years], fontsize=8)
    ax.set_xlabel("Census year", fontsize=8, color="#555555", labelpad=4)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.2f"))
    if ylim is not None:
        ax.set_ylim(*ylim)


def _shorten_prefix(prefix: str) -> str:
    return (
        prefix
        .replace("white_black", "wb")
        .replace("white_poc", "wpoc")
        .replace("block_groups", "bg")
    )
