from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from pipeline.utils.visualization_settings import GRID_METRICS, _apply_panel_style


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
