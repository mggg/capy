from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd
import typer

try:
    from .parse_output import enrich_metrics
except ImportError:
    from parse_output import enrich_metrics

# Okabe-Ito colorblind-safe palette, extended to 10
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


def _short_name(cbsa_title: str) -> str:
    """'Atlanta-Sandy Springs-Alpharetta, GA' → 'Atlanta, GA'"""
    city_part, _, state = cbsa_title.rpartition(", ")
    return f"{city_part.split('-')[0]}, {state}"


METRICS = ["e_assort",
            "he_assort",
            "skew_self_0",
            "skew_other_0",
            "edge_0",
            "skew'_self_0",	
            "skew'_other_0",
            "half_edge_0",
            "skew_self_exact_0",
            "skew_other_exact_0",
            "edge_exact_0",	
            "skew'_self_exact_0",
            "skew'_other_exact_0",
            "half_edge_exact_0",	
            "skew_self_0.5",	
            "skew_other_0.5",	
            "edge_0.5",
            "skew'_self_0.5",
            "skew'_other_0.5",	
            "half_edge_0.5",
            "skew_self_exact_0.5",
            "skew_other_exact_0.5",	
            "edge_exact_0.5",	
            "skew'_self_exact_0.5",
            "skew'_other_exact_0.5",
            "half_edge_exact_0.5",
            "skew_self_1",
            "skew_other_1",
            "edge_1",
            "skew'_self_1",
            "skew'_other_1",
            "half_edge_1",
            "skew_self_exact_1",
            "skew_other_exact_1",
            "edge_exact_1",
            "skew'_self_exact_1",
            "skew'_other_exact_1",
            "half_edge_exact_1",
            "skew_self_2",
            "skew_other_2",
            "edge_2",
            "skew'_self_2",
            "skew'_other_2",
            "half_edge_2",
            "skew_self_exact_2",
            "skew_other_exact_2",
            "edge_exact_2",
            "skew'_self_exact_2",
            "skew'_other_exact_2",
            "half_edge_exact_2",
            "skew_self_10",
            "skew_other_10",
            "edge_10",
            "skew'_self_10",
            "skew'_other_10",
            "half_edge_10",
            "skew_self_exact_10",
            "skew_other_exact_10",
            "edge_exact_10",
            "skew'_self_exact_10",
            "skew'_other_exact_10",
            "half_edge_exact_10",
            "skew_self_lim",
            "skew_other_lim",
            "edge_lim",
            "skew'_self_lim",
            "skew'_other_lim",
            "half_edge_lim",	
            "skew_self_exact_lim",
            "skew_other_exact_lim",	
            "edge_exact_lim",
            "skew'_self_exact_lim",
            "skew'_other_exact_lim",
            "half_edge_exact_lim",
            "dissimilarity_1",
            "dissimilarity_2",	
            "dissimilarity_10",
            "gini",	
            "moran_A",	
            "moran_P",	
            "moran_L",
            "moran_M",
            "moran_D_1",
            "moran_D_2"
            "moran_A_white",	
            "moran_P_white",
            "moran_L_white",
            "moran_M_white",
            "moran_D_1_white",
            "moran_D_2_white"
            ]

def _apply_panel_style(ax, years: list, ylim: tuple) -> None:
    """Apply shared panel style: background, gridlines, spines, ticks, y-limits."""
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


def plot_grid_top10(
    df: pd.DataFrame,
    prefix: str,
    month_year: str,
    output_dir: Path,
    n: int = 10,
    geography_label: str = "tracts",
    fixed_y: bool = False,
) -> None:
    BG = "#fafafa"
    month_year_df = df[df["definition_month_year"] == month_year]
    top_n_metros = list(month_year_df["cbsa_title"].drop_duplicates()[:n])
    plot_df = (
        month_year_df[month_year_df["cbsa_title"].isin(top_n_metros)]
        .sort_values(["cbsa_title", "year"])
    )

    available = [m for m in GRID_METRICS if m in plot_df.columns]
    if not available:
        return

    color_map = {cbsa: PALETTE[i % len(PALETTE)] for i, cbsa in enumerate(top_n_metros)}
    years = sorted(plot_df["year"].unique())
    n_cols = len(available)
    ylim = (plot_df[available].min().min(), plot_df[available].max().max()) if fixed_y else None

    fig, axes = plt.subplots(1, n_cols, figsize=(5 * n_cols, 5), facecolor=BG, sharey=False)
    if n_cols == 1:
        axes = [axes]

    for ax, metric in zip(axes, available):
        _apply_panel_style(ax, years, ylim)
        ax.set_title(GRID_METRICS[metric], fontsize=11, fontweight="bold", pad=8, color="#111111")
        for cbsa in top_n_metros:
            cbsa_df = plot_df[plot_df["cbsa_title"] == cbsa]
            ax.plot(
                cbsa_df["year"], cbsa_df[metric],
                color=color_map[cbsa], linewidth=1.8, marker="o", markersize=4, zorder=2,
            )

    pair_label = "White–Black" if prefix.startswith("wb") else "White–POC"
    fig.suptitle(
        f"Segregation over time: {pair_label}",
        fontsize=14, fontweight="bold", color="#111111", y=1.04,
    )
    fig.text(
        0.5, 0.97,
        f"Top {n} U.S. metros by 2020 population · Census {geography_label} within CBSAs",
        ha="center", fontsize=9, color="#555555",
    )

    handles = [
        plt.Line2D([0], [0], color=color_map[c], linewidth=2.5, label=_short_name(c))
        for c in top_n_metros
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=min(5, len(top_n_metros)),
        bbox_to_anchor=(0.5, -0.13),
        frameon=False,
        fontsize=8,
        handlelength=1.5,
        columnspacing=1.0,
        labelcolor="#333333",
    )
    fig.text(
        0.5, -0.22,
        "Notes: Moran's I uses weights matrix P. Half Edge uses λ=1.\n"
        "Sources: Decennial census and TIGER/Line shapefiles via Census API (2000-2020) and NHGIS (1980-1990).",
        ha="center", fontsize=7, color="#383838", linespacing=1.6,
    )

    grid_dir = output_dir / "grid_lineplots"
    grid_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        grid_dir / f"{prefix}_top10.png",
        dpi=150, bbox_inches="tight", facecolor=BG,
    )
    plt.close(fig)


def plot_grid_all(
    df: pd.DataFrame,
    prefix: str,
    month_year: str,
    output_dir: Path,
    geography_label: str = "tracts",
    fixed_y: bool = False,
) -> None:
    BG = "#fafafa"
    month_year_df = df[df["definition_month_year"] == month_year]

    available = [m for m in GRID_METRICS if m in month_year_df.columns]
    if not available:
        return

    years = sorted(month_year_df["year"].unique())
    all_cbsas = month_year_df["cbsa_title"].unique()
    ylim = (month_year_df[available].min().min(), month_year_df[available].max().max()) if fixed_y else None

    yearly_mean = month_year_df.groupby("year")[list(available)].mean().reindex(years)

    n_cols = len(available)
    fig, axes = plt.subplots(1, n_cols, figsize=(5 * n_cols, 5), facecolor=BG, sharey=False)
    if n_cols == 1:
        axes = [axes]

    for ax, metric in zip(axes, available):
        _apply_panel_style(ax, years, ylim)
        ax.set_title(GRID_METRICS[metric], fontsize=11, fontweight="bold", pad=8, color="#111111")

        for cbsa in all_cbsas:
            cbsa_df = month_year_df[month_year_df["cbsa_title"] == cbsa].sort_values("year")
            ax.plot(
                cbsa_df["year"], cbsa_df[metric],
                color="#aaaaaa", linewidth=0.7, alpha=0.4, zorder=1,
            )
        ax.plot(
            yearly_mean.index, yearly_mean[metric],
            color="#0072b2", linewidth=2.4, marker="o", markersize=5, zorder=3,
        )

    pair_label = "White–Black" if prefix.startswith("wb") else "White–POC"
    fig.suptitle(
        f"Segregation over time: {pair_label}",
        fontsize=14, fontweight="bold", color="#111111", y=1.04,
    )
    fig.text(
        0.5, 0.95,
        f"All U.S. CBSAs · Census {geography_label} in CBSAs · Mean across all CBSAs in blue",
        ha="center", fontsize=9, color="#555555",
    )

    handles = [
        plt.Line2D([0], [0], color="#aaaaaa", linewidth=1.5, alpha=0.6, label="Individual CBSA"),
        plt.Line2D([0], [0], color="#0072b2", linewidth=2.4, marker="o", markersize=5, label="Mean across all CBSAs"),
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=2,
        bbox_to_anchor=(0.5, -0.08),
        frameon=False,
        fontsize=8,
        handlelength=1.5,
        columnspacing=1.5,
        labelcolor="#333333",
    )
    fig.text(
        0.5, -0.16,
        "Notes: Moran's I uses weights matrix P. Half Edge uses λ=1.\n"
        "Sources: Decennial census and TIGER/Line shapefiles via Census API (2000-2020) and NHGIS (1980-1990).",
        ha="center", fontsize=7, color="#383838", linespacing=1.6,
    )

    grid_dir = output_dir / "grid_lineplots"
    grid_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        grid_dir / f"{prefix}_all_cbsa.png",
        dpi=150, bbox_inches="tight", facecolor=BG,
    )
    plt.close(fig)


def plot_family_grids(
    df: pd.DataFrame,
    prefix: str,
    month_year: str,
    output_dir: Path,
    n: int = 10,
    n_cols: int = 6,
    geography_label: str = "tracts",
    fixed_y: bool = False,
) -> None:
    BG = "#fafafa"
    month_year_df = df[df["definition_month_year"] == month_year]
    top_n_metros = list(month_year_df["cbsa_title"].drop_duplicates()[:n])
    plot_df = (
        month_year_df[month_year_df["cbsa_title"].isin(top_n_metros)]
        .sort_values(["cbsa_title", "year"])
    )

    color_map = {cbsa: PALETTE[i % len(PALETTE)] for i, cbsa in enumerate(top_n_metros)}
    years = sorted(plot_df["year"].unique())
    pair_label = "White–Black" if prefix.startswith("wb") else "White–POC"

    # Group available metrics by family title from METRIC_LABELS.
    families: dict = {}
    for metric in METRICS:
        if metric not in plot_df.columns:
            continue
        title, subtitle = METRIC_LABELS.get(metric, (metric.replace("_", " ").title(), ""))
        families.setdefault(title, []).append((metric, subtitle))

    family_dir = output_dir / "metric_family_grids"
    family_dir.mkdir(parents=True, exist_ok=True)

    handles = [
        plt.Line2D([0], [0], color=color_map[c], linewidth=2.5, label=_short_name(c))
        for c in top_n_metros
    ]

    for family_title, members in families.items():
        n_metrics = len(members)
        cols = min(n_metrics, n_cols)
        rows = (n_metrics + cols - 1) // cols
        family_metrics = [m for m, _ in members]
        ylim = (plot_df[family_metrics].min().min(), plot_df[family_metrics].max().max()) if fixed_y else None

        fig, axes = plt.subplots(
            rows, cols,
            figsize=(5 * cols, 5 * rows),
            facecolor=BG,
            sharey=False,
            squeeze=False,
        )

        for idx, (metric, subtitle) in enumerate(members):
            ax = axes[idx // cols][idx % cols]
            _apply_panel_style(ax, years, ylim)
            ax.set_title(
                subtitle if subtitle else family_title,
                fontsize=10, fontweight="bold", pad=8, color="#111111",
            )
            for cbsa in top_n_metros:
                cbsa_df = plot_df[plot_df["cbsa_title"] == cbsa]
                ax.plot(
                    cbsa_df["year"], cbsa_df[metric],
                    color=color_map[cbsa], linewidth=1.8, marker="o", markersize=4, zorder=2,
                )

        for idx in range(n_metrics, rows * cols):
            axes[idx // cols][idx % cols].set_visible(False)

        SUPTITLE_Y = 1.02
        fig.suptitle(
            f"{family_title} · Segregation over time: {pair_label}",
            fontsize=14, fontweight="bold", color="#111111", y=SUPTITLE_Y,
        )
        fig.legend(
            handles=handles,
            loc="lower center",
            ncol=min(5, len(top_n_metros)),
            bbox_to_anchor=(0.5, -0.03),
            frameon=False,
            fontsize=8,
            handlelength=1.5,
            columnspacing=1.0,
            labelcolor="#333333",
        )
        # Anchor subtitle a constant 20pt below the suptitle centre, converting
        # points → figure-fraction so it stays visually fixed across row counts.
        subtitle_y = SUPTITLE_Y - 20 / (72 * fig.get_figheight())
        fig.text(
            0.5, subtitle_y,
            f"Top {n} U.S. metros by 2020 population · Census {geography_label} in CBSAs",
            ha="center", va="top", fontsize=9, color="#555555",
        )

        safe_name = (
            family_title.lower()
            .replace("'", "").replace("(", "").replace(")", "")
            .replace(" ", "_")
        )
        fig.savefig(
            family_dir / f"{prefix}_{safe_name}.png",
            dpi=150, bbox_inches="tight", facecolor=BG,
        )
        plt.close(fig)


def _shorten_prefix(prefix: str) -> str:
    return (
        prefix
        .replace("white_black", "wb")
        .replace("white_poc", "wpoc")
        .replace("block_groups", "bg")
    )


def ensure_metadata(df: pd.DataFrame) -> pd.DataFrame:
    required = {"definition_month_year", "year", "cbsa_title", "total_population_2020"}
    if required.issubset(df.columns):
        return df
    return enrich_metrics(df)


def main(
    filename: str = "outputs/white_poc_parsed.csv",
    n: int = 10,
    prefix: str = "white_poc",
    geography_type: Optional[str] = None,
    fixed_y: bool = False,
):
    if geography_type is None:
        for geo in ("block_groups", "blocks", "tracts", "counties"):
            if geo in prefix:
                geography_type = geo
                break
        else:
            geography_type = "tracts"
    geography_label = geography_type.replace("_", " ")

    prefix = _shorten_prefix(prefix)
    output_dir = Path(filename).parent / "figures"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "lineplots").mkdir(exist_ok=True)

    df = ensure_metadata(pd.read_csv(filename))
    df = df.sort_values("total_population_2020", ascending=False)

    BG = "#fafafa"
    pair_label = "White–Black" if prefix.startswith("wb") else "White–POC"

    for month_year in set(df["definition_month_year"]):
        month_year_df = df[df["definition_month_year"] == month_year]
        # vintage_label = month_year.replace("_", " ").title()

        top_n_metros = list(month_year_df["cbsa_title"].drop_duplicates()[:n])
        top_n_df = month_year_df[
            month_year_df["cbsa_title"].isin(top_n_metros)
        ].sort_values(["cbsa_title", "year"])

        color_map = {cbsa: PALETTE[i % len(PALETTE)] for i, cbsa in enumerate(top_n_metros)}
        years = sorted(top_n_df["year"].unique())

        for metric in METRICS:
            if metric not in top_n_df.columns:
                continue

            fig, ax = plt.subplots(figsize=(6, 6), facecolor=BG)
            _apply_panel_style(ax, years, None)

            for cbsa in top_n_metros:
                cbsa_df = top_n_df[top_n_df["cbsa_title"] == cbsa]
                ax.plot(
                    cbsa_df["year"], cbsa_df[metric],
                    color=color_map[cbsa], linewidth=1.8, marker="o", markersize=4, zorder=2,
                )

            title, subtitle = METRIC_LABELS.get(metric, (metric.replace("_", " ").title(), ""))
            ax.set_title(title, fontsize=13, fontweight="bold",
                         pad=30 if subtitle else 10, color="#111111")
            if subtitle:
                ax.text(0.5, 1.04, subtitle, transform=ax.transAxes,
                        ha="center", va="bottom", fontsize=9, color="#777777")
            fig.suptitle(
                f"Segregation over time: {pair_label}",
                fontsize=14, fontweight="bold", color="#111111", y=1.06,
            )
            fig.text(
                0.5, 1,
                f"Top {n} U.S. metros by 2020 population · Census {geography_label} in CBSAs",
                ha="center", fontsize=9, color="#555555",
            )

            handles = [
                plt.Line2D([0], [0], color=color_map[c], linewidth=2.5, label=_short_name(c))
                for c in top_n_metros
            ]
            fig.legend(
                handles=handles,
                loc="lower center",
                ncol=min(5, len(top_n_metros)),
                bbox_to_anchor=(0.5, -0.1),
                frameon=False,
                fontsize=8,
                handlelength=1.5,
                columnspacing=1.0,
                labelcolor="#333333",
            )

            fig.savefig(
                output_dir / "lineplots" / f"{prefix}_{metric}.png",
                dpi=150, bbox_inches="tight", facecolor=BG,
            )
            plt.close(fig)

        plot_grid_top10(df, prefix, month_year, output_dir, n, geography_label=geography_label, fixed_y=fixed_y)
        plot_grid_all(df, prefix, month_year, output_dir, geography_label=geography_label, fixed_y=fixed_y)
        plot_family_grids(df, prefix, month_year, output_dir, n, geography_label=geography_label, fixed_y=fixed_y)


if __name__ == "__main__":
    typer.run(main)
