import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import matplotlib.pyplot as plt
import pandas as pd
import typer

from pipeline.process_results import enrich_metrics
from pipeline.utils.visualization_settings import (
    METRIC_LABELS,
    METRICS,
    PALETTE,
    _apply_panel_style,
    _shorten_prefix,
    _short_name,
)
from pipeline.visualization.plot_family_grids import plot_family_grids
from pipeline.visualization.plot_grid_all import plot_grid_all
from pipeline.visualization.plot_grid_top10 import plot_grid_top10


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
