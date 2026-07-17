from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from pipeline.utils.visualization_settings import (
    GRID_METRICS,
    PALETTE,
    _apply_panel_style,
    _short_name,
)


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
