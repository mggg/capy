from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from pipeline.utils.visualization_settings import GRID_METRICS, _apply_panel_style


def plot_single_metric(df: pd.DataFrame, prefix: str, month_year: str, output_dir: Path, geography_label: str = "tracts", area_label: str = "CBSA", fixed_y: bool = False) -> None:
    MIN_POPULATION = 100_000
    if "Cities" in area_label:
        MIN_POPULATION = 0

    BG = "#fafafa"
    month_year_df = df[df["definition_month_year"] == month_year]

    available = [m for m in GRID_METRICS if m in month_year_df.columns]
    if not available:
        return

    years = sorted(month_year_df["year"].unique())

    cbsa_year_counts = month_year_df.groupby("area_code")["year"].nunique()
    complete_cbsas = cbsa_year_counts[cbsa_year_counts == len(years)].index
    cbsa_pop = month_year_df.drop_duplicates("area_code").set_index("area_code")["total_population_2020"]
    eligible_cbsas = complete_cbsas[cbsa_pop.reindex(complete_cbsas).fillna(0) >= MIN_POPULATION]

    month_year_df = month_year_df[month_year_df["area_code"].isin(eligible_cbsas)]
    all_cbsas = eligible_cbsas

    ylim = (month_year_df[available].min().min(), month_year_df[available].max().max()) if fixed_y else None

    yearly_mean = month_year_df.groupby("year")[list(available)].mean().reindex(years)

    n_cols = len(available)
    fig, axes = plt.subplots(1, n_cols, figsize=(5 * n_cols, 5), facecolor=BG, sharey=False)
    if n_cols == 1:
        axes = [axes]

    for ax, metric in zip(axes, available):
        y_range = month_year_df[metric].max() - month_year_df[metric].min()
        _apply_panel_style(ax, years, ylim, y_range=y_range)
        # ax.set_title(GRID_METRICS[metric], fontsize=11, fontweight="bold", pad=8, color="#111111")

        for cbsa in all_cbsas:
            cbsa_df = month_year_df[month_year_df["area_code"] == cbsa].sort_values("year")
            ax.plot(
                cbsa_df["year"], cbsa_df[metric],
                color="#aaaaaa", linewidth=0.7, alpha=0.4, zorder=1)
        ax.plot(yearly_mean.index, yearly_mean[metric],
            color="#0072b2", linewidth=2.4, marker="o", markersize=5, zorder=3, alpha=0.8)

    pair_label = "White–Black" if prefix.startswith("wb") else "White–POC"
    # fig.suptitle(f"Segregation over time: {pair_label}",
    #     fontsize=14, fontweight="bold", color="#111111", y=1.04)
    # if "cities" in area_label:
    #     fig.text(0.5, 0.95, f"Segregation metrics in {area_label}, present in all years ({len(eligible_cbsas)}). Mean in blue.", ha="center", fontsize=9, color="#555555")
    # else:
    #     fig.text(0.5, 0.95, f"{len(eligible_cbsas)} {area_label} ≥100k pop., present in all years. Census {geography_label} in {area_label}. Mean in blue.", ha="center", fontsize=9, color="#555555")

    handles = [plt.Line2D([0], [0], color="#aaaaaa", linewidth=1.5, alpha=0.6, label="Individual area"),
        plt.Line2D([0], [0], color="#0072b2", linewidth=2.4, marker="o", markersize=5, label="Mean across all areas")]
    fig.legend(handles=handles, loc="lower center", ncol=2, bbox_to_anchor=(0.5, -0.04), frameon=False, fontsize=8, handlelength=1.5, columnspacing=1.5, labelcolor="#333333")
    # fig.text(0.5, -0.16,
    #         f"Notes: Calculated using Census {geography_label} in {area_label}.\n"
    #         # Moran's I uses weights matrix P. Half Edge uses λ=1.\n"
    #          "Sources: Decennial census and TIGER/Line shapefiles via Census API (2000-2020) and NHGIS (before 2000).", ha="center", fontsize=7, color="#383838", linespacing=1.6)

    grid_dir = output_dir / "grid_lineplots"
    grid_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(grid_dir / f"{prefix}_all_cbsa.png", dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
