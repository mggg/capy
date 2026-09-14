import sys
from pathlib import Path
import textwrap
import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))  # project root
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # experiment_code/baseline/

from typing import Optional
import typer
from capy_core.process_results import enrich_metrics
from visualization.visualization_settings import _shorten_prefix
from visualization.visualization_settings import (GRID_METRICS, PALETTE, _apply_panel_style, _short_name)



def plot_grid_top10(df: pd.DataFrame, prefix: str, month_year: str, output_dir: Path, n: int = 10, geography_label: str = "tracts", area_label: str = "CBSA", fixed_y: bool = False) -> None:
    month_year_df = df[df["definition_month_year"] == month_year]
    top_n_metros = list(month_year_df["area_code"].drop_duplicates()[:n])
    code_to_title = month_year_df.drop_duplicates("area_code").set_index("area_code")["area_title"]
    plot_df = (
        month_year_df[month_year_df["area_code"].isin(top_n_metros)]
        .sort_values(["area_code", "year"]))

    available = [m for m in GRID_METRICS if m in plot_df.columns]
    if not available:
        return

    color_map = {cbsa: PALETTE[i % len(PALETTE)] for i, cbsa in enumerate(top_n_metros)}
    years = sorted(plot_df["year"].unique())
    n_cols = len(available)
    ylim = (plot_df[available].min().min(), plot_df[available].max().max()) if fixed_y else None

    fig, axes = plt.subplots(1, n_cols, figsize=(5 * n_cols, 5), sharey=False, gridspec_kw={"wspace": 0.3})
    if n_cols == 1:
        axes = [axes]

    for ax, metric in zip(axes, available):
        y_range = plot_df[metric].max() - plot_df[metric].min()
        _apply_panel_style(ax, years, ylim, y_range=y_range)
        for cbsa in top_n_metros:
            cbsa_df = plot_df[plot_df["area_code"] == cbsa]
            ax.plot(
                cbsa_df["year"], cbsa_df[metric],
                color=color_map[cbsa], linewidth=1.8, marker="o", markersize=4, zorder=2, alpha=0.8)

    # pair_label = "White–Black" if prefix.startswith("wb") else "White–POC"
    # fig.suptitle(
    #     f"Segregation over time: {pair_label}",
    #     fontsize=14, fontweight="bold", color="#111111", y=1.04)
    # fig.text(0.5, 0.97,
    #     f"Segregation metrics in top {n} {area_label} by 2020 population.", ha="center", fontsize=9, color="#555555")

    # wrap metro area names at a character limit
    handles = [plt.Line2D([0], [0], color=color_map[c], linewidth=2.5, 
                          label=textwrap.fill(_short_name(code_to_title[c]), width=17)) for c in top_n_metros]
    fig.legend(handles=handles,
           loc="center left",
           bbox_to_anchor=(1.06, 0.5),
           bbox_transform=axes[-1].transAxes, # coordinates relative to axes, not figure
           frameon=False, fontsize=14,
           labelcolor="#333333")
    # fig.text(0.5, -0.22,
    #     f"Notes: Calculated using Census {geography_label} in {area_label}.\n"
    #     "Sources: Decennial census and TIGER/Line shapefiles via Census API (2000-2020) and NHGIS (before 2000).",
    #     ha="center", fontsize=7, color="#383838", linespacing=1.6)

    grid_dir = output_dir / "grid_lineplots"
    grid_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        grid_dir / f"{prefix}_moran_d_capy_top10.png",
        bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    def main(filename: str, prefix: str = "white_poc",
             study_area_type: Optional[str] = None,
             n: int = 10, fixed_y: bool = False):

        area_label = {"max_county": "most populous counties within CBSAs", "max_city": "most populous cities within CBSAs"}.get(study_area_type, "CBSAs")

        geography_type = next((g for g in ("block_groups", "blocks", "tracts", "counties") if g in prefix), "tracts")

        geography_label = geography_type.replace("_", " ")
        prefix = _shorten_prefix(prefix)

        output_dir = Path("figures") / "baseline" / f"{geography_type}_in_{study_area_type or 'cbsa'}"
        output_dir.mkdir(parents=True, exist_ok=True)

        df = enrich_metrics(pd.read_csv(filename)).sort_values("total_population_2020", ascending=False)
        month_year = df["definition_month_year"].iloc[0]
        
        plot_grid_top10(df, prefix, month_year, output_dir, n,
                        geography_label=geography_label, area_label=area_label, fixed_y=fixed_y)

    typer.run(main)
