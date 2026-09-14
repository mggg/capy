"""
One multi-panel figure per metric family (e.g. all Capy variants, all Moran variants).

Panels within a family share the same suptitle; each panel is labelled by its subtitle
from METRIC_LABELS. Top-N metros are coloured by PALETTE. Called by generate_figures.main;
not intended to be run directly.

Output: {output_dir}/metric_family_grids/{prefix}_{family_name}.png
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
from visualization.visualization_settings import (METRIC_LABELS, METRICS, PALETTE, _apply_panel_style, _short_name)


def plot_family_grids(df: pd.DataFrame, prefix: str, month_year: str, output_dir: Path, n: int = 10, n_cols: int = 6, geography_label: str = "tracts", area_label: str = "CBSA", fixed_y: bool = False) -> None:
    month_year_df = df[df["definition_month_year"] == month_year]
    top_n_metros = list(month_year_df["area_code"].drop_duplicates()[:n])
    code_to_title = month_year_df.drop_duplicates("area_code").set_index("area_code")["area_title"]
    plot_df = (month_year_df[month_year_df["area_code"].isin(top_n_metros)].sort_values(["area_code", "year"]))

    color_map = {cbsa: PALETTE[i % len(PALETTE)] for i, cbsa in enumerate(top_n_metros)}
    years = sorted(plot_df["year"].unique())
    pair_label = "White–Black" if prefix.startswith("wb") else "White–POC"

    families: dict = {}
    for metric in METRICS:
        if metric not in plot_df.columns:
            continue
        title, subtitle = METRIC_LABELS.get(metric, (metric.replace("_", " ").title(), ""))
        families.setdefault(title, []).append((metric, subtitle))

    family_dir = output_dir / "metric_family_grids"
    family_dir.mkdir(parents=True, exist_ok=True)

    handles = [plt.Line2D([0], [0], color=color_map[c], linewidth=2.5, label=_short_name(code_to_title[c]))
        for c in top_n_metros]

    for family_title, members in families.items():
        n_metrics = len(members)
        cols = min(n_metrics, n_cols)
        rows = (n_metrics + cols - 1) // cols
        family_metrics = [m for m, _ in members]
        ylim = (plot_df[family_metrics].min().min(), plot_df[family_metrics].max().max()) if fixed_y else None

        fig, axes = plt.subplots(
            rows, cols,
            figsize=(5 * cols, 5 * rows),
            sharey=False,
            squeeze=False)

        for idx, (metric, subtitle) in enumerate(members):
            ax = axes[idx // cols][idx % cols]
            y_range = plot_df[metric].max() - plot_df[metric].min()
            _apply_panel_style(ax, years, ylim, y_range=y_range)
            for cbsa in top_n_metros:
                cbsa_df = plot_df[plot_df["area_code"] == cbsa]
                ax.plot(
                    cbsa_df["year"], cbsa_df[metric],
                    color=color_map[cbsa], linewidth=1.8, marker="o", markersize=4, zorder=2, alpha=0.8)

        for idx in range(n_metrics, rows * cols):
            axes[idx // cols][idx % cols].set_visible(False)

        SUPTITLE_Y = 1.02
        fig.suptitle(f"{family_title}. Segregation over time: {pair_label}", fontsize=14, fontweight="bold", color="#111111", y=SUPTITLE_Y)
        fig.legend(handles=handles, loc="lower center", ncol=min(5, len(top_n_metros)), bbox_to_anchor=(0.5, -0.03), frameon=False, fontsize=8, handlelength=1.5, columnspacing=1.0, labelcolor="#333333")
        subtitle_y = SUPTITLE_Y - 20 / (72 * fig.get_figheight())
        fig.text(0.5, subtitle_y,
            f"Top {n} U.S. metros by 2020 population. Census {geography_label} in {area_label}",
            ha="center", va="top", fontsize=9, color="#555555")

        safe_name = (family_title.lower().replace("'", "").replace("(", "").replace(")", "").replace(" ", "_"))
        fig.savefig(family_dir / f"{prefix}_{safe_name}.png",
            bbox_inches="tight")
        plt.close(fig)


if __name__ == "__main__":
    def main(filename: str, prefix: str = "white_poc",
             study_area_type: Optional[str] = None,
             n: int = 10, fixed_y: bool = False):
        area_label = {"max_county": "most populous counties within CBSAs",
                      "max_city": "most populous cities within CBSAs"}.get(study_area_type, "CBSAs")
        geography_type = next((g for g in ("block_groups", "blocks", "tracts", "counties") if g in prefix), "tracts")
        geography_label = geography_type.replace("_", " ")
        prefix = _shorten_prefix(prefix)
        output_dir = Path("figures") / "baseline" / f"{geography_type}_in_{study_area_type or 'cbsa'}"
        output_dir.mkdir(parents=True, exist_ok=True)
        df = enrich_metrics(pd.read_csv(filename)).sort_values("total_population_2020", ascending=False)
        month_year = df["definition_month_year"].iloc[0]
        plot_family_grids(df, prefix, month_year, output_dir, n,
                          geography_label=geography_label, area_label=area_label, fixed_y=fixed_y)

    typer.run(main)
