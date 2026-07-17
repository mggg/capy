from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from pipeline.utils.visualization_settings import (
    METRIC_LABELS,
    METRICS,
    PALETTE,
    _apply_panel_style,
    _short_name,
)


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
            y_range = plot_df[metric].max() - plot_df[metric].min()
            _apply_panel_style(ax, years, ylim, y_range=y_range)
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
