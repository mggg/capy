"""
Creates a trace plot figure of all eligible census areas and shows their segregation metrics over time.
Eligible areas are those with ≥100k population in 2020 and present in all observed years.

Output: {output_dir}/grid_lineplots/{prefix}_moran_d_capy_all_cbsa.png
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))  # project root
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # experiment_code/baseline/

from typing import Optional
import typer
from capy_core.process_results import enrich_metrics
from visualization.visualization_settings import _shorten_prefix
from visualization.visualization_settings import GRID_METRICS, _apply_panel_style


def plot_grid_all_census_areas(df: pd.DataFrame, prefix: str, month_year: str, output_dir: Path, geography_label: str = "tracts", area_label: str = "CBSA", fixed_y: bool = False) -> None:
    MIN_POPULATION = 100_000
    if "Cities" in area_label:
        MIN_POPULATION = 0

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
    fig, axes = plt.subplots(1, n_cols, figsize=(5 * n_cols, 5), sharey=False, gridspec_kw={"wspace": 0.3})
    if n_cols == 1:
        axes = [axes]

    for ax, metric in zip(axes, available):
        y_range = month_year_df[metric].max() - month_year_df[metric].min()
        _apply_panel_style(ax, years, ylim, y_range=y_range)

        for cbsa in all_cbsas:
            cbsa_df = month_year_df[month_year_df["area_code"] == cbsa].sort_values("year")
            ax.plot(
                cbsa_df["year"], cbsa_df[metric],
                color="#7cb3f6", linewidth=0.7, alpha=0.4, zorder=1)
        ax.plot(yearly_mean.index, yearly_mean[metric],
            color="#1560bd", linewidth=2.4, marker="o", markersize=5, zorder=3)

    pair_label = "White–Black" if prefix.startswith("wb") else "White–POC"
    # fig.suptitle(f"Segregation over time: {pair_label}",
    #     fontsize=14, fontweight="bold", color="#111111", y=1.04)
    # if "cities" in area_label:
    #     fig.text(0.5, 0.95, f"Segregation metrics in {area_label}, present in all years ({len(eligible_cbsas)}). Mean in blue.", ha="center", fontsize=9, color="#555555")
    # else:
    #     fig.text(0.5, 0.95, f"{len(eligible_cbsas)} {area_label} ≥100k pop., present in all years. Census {geography_label} in {area_label}. Mean in blue.", ha="center", fontsize=9, color="#555555")

    handles = [plt.Line2D([0], [0], color="#7cb3f6", linewidth=1.5, alpha=0.6, label="Individual area"),
        plt.Line2D([0], [0], color="#1560bd", linewidth=2.4, marker="o", markersize=5, label="Mean across areas")]
    fig.legend(handles=handles, loc="center left",
               bbox_to_anchor=(1.06, 0.5),
               bbox_transform=axes[-1].transAxes, # coordinates relative to last axes, not figure
               frameon=False, fontsize=14, labelcolor="#333333")
    # fig.text(0.5, -0.16,
    #         f"Notes: Calculated using Census {geography_label} in {area_label}.\n"
    #         # Moran's I uses weights matrix P. Half Edge uses λ=1.\n"
    #          "Sources: Decennial census and TIGER/Line shapefiles via Census API (2000-2020) and NHGIS (before 2000).", ha="center", fontsize=7, color="#383838", linespacing=1.6)

    grid_dir = output_dir / "grid_lineplots"
    grid_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(grid_dir / f"{prefix}_moran_d_capy_all_cbsa.png", bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    def main(filename: str, prefix: str = "white_poc",
             study_area_type: Optional[str] = None,
             fixed_y: bool = False):
        area_label = {"max_county": "most populous counties within CBSAs",
                      "max_city": "most populous cities within CBSAs"}.get(study_area_type, "CBSAs")
        geography_type = next((g for g in ("block_groups", "blocks", "tracts", "counties") if g in prefix), "tracts")
        geography_label = geography_type.replace("_", " ")
        prefix = _shorten_prefix(prefix)
        output_dir = Path("figures") / "baseline" / f"{geography_type}_in_{study_area_type or 'cbsa'}"
        output_dir.mkdir(parents=True, exist_ok=True)
        df = enrich_metrics(pd.read_csv(filename)).sort_values("total_population_2020", ascending=False)
        month_year = df["definition_month_year"].iloc[0]
        plot_grid_all_census_areas(df, prefix, month_year, output_dir,
                                   geography_label=geography_label, area_label=area_label, fixed_y=fixed_y)

    typer.run(main)
