"""Create one scatter plot per metric against minority population share.

The input CSV normally lives under data/shared/outputs/<geography>_in_<study_area>/,
which determines the figure output directory. Only study areas represented in all
five decades and with population above 100,000 are included.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))  # project root (for capy_core)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # experiment_code/baseline/ (for visualization)

import matplotlib.lines as mlines
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import typer

from capy_core.process_results import join_study_area_metadata
from experiment_code.visualization_settings import GRID_COLOR, PRIMARY_INK, SECONDARY, GRID_METRICS, YEAR_COLORS


POPULATION_THRESHOLD = 100_000 # only include CBSAs with population > 100K
ALL_YEARS = {1980, 1990, 2000, 2010, 2020}

# theoretical minimum of capy for reference in plots, if we decide to include it. for now we don't know.
def minimum_capy(x):
    return # formula

def plot_metrics_vs_rho(filename: str, output_dir: str = "") -> None:
    path_to_file = filename
    csv = Path(path_to_file)

    df = join_study_area_metadata(pd.read_csv(csv))
    if "white_poc" in path_to_file:
        df["rho"] = df["total_poc"] / (df["total_poc"] + df["total_white"])
        prefix = "wpoc"
    elif "white_black" in path_to_file:
        df["rho"] = df["total_black"] / (df["total_black"] + df["total_white"])
        prefix = "wb"
    else:
        raise ValueError("Unknown file type: expected white_poc or white_black in filename")

    years = sorted(df["year"].unique())
    missing_years = sorted(set(years) - YEAR_COLORS.keys())
    if missing_years:
        raise ValueError(
            f"Missing colors for years {missing_years}; add them to YEAR_COLORS in visualization_settings.py")

    # select CBSAs present in all 5 decades with population > 100K
    has_all_years = df.groupby("area_code")["year"].apply(lambda s: ALL_YEARS.issubset(set(s)))
    cbsas_all_years = has_all_years[has_all_years].index

    min_pop = df.groupby("area_code")["total_population"].min()
    cbsas_large = min_pop[min_pop > POPULATION_THRESHOLD].index
    valid_cbsas = cbsas_all_years.intersection(cbsas_large)
    df = df[df["area_code"].isin(valid_cbsas)]
    if df.empty:
        raise ValueError(
            "No observations remain after requiring study areas to be present in "
            f"{sorted(ALL_YEARS)} and have population above {POPULATION_THRESHOLD:,} in every year.")

    columns = ["half_edge_1", "moran_P", "dissimilarity_1"]

    if output_dir:
        out_dir = Path(output_dir)
    else:
        geography_type, separator, study_area_type = csv.parent.name.partition("_in_")
        if not separator or not geography_type or not study_area_type:
            raise ValueError(
                f"Expected CSV inside a '<geography>_in_<study_area>' directory: {csv}")
        out_dir = Path("figures") / "baseline" / csv.parent.name / "metrics_vs_rho"
    out_dir.mkdir(parents=True, exist_ok=True)

    for col in columns:
        fig, ax = plot_rho_metric(df, col, years)

        out = out_dir / f"{prefix}_{GRID_METRICS[col].split(" ")[0].lower().replace("'", '')}.png"
        fig.savefig(out, dpi=300, bbox_inches="tight")
        plt.close(fig)
        print(f"Saved to {out}")

    save_rho_metrics_legend(years, out_dir, prefix)


def plot_rho_metric(df, col, years):
    """Draw one metric against minority share and return its figure and axes."""
    fig, ax = plt.subplots(figsize=(7, 6.8))
    ax.spines[["top", "right", "left", "bottom"]].set_visible(False)
    ax.grid(color=GRID_COLOR, linewidth=0.8, zorder=0)
    ax.tick_params(length=0, labelsize=18, labelcolor=SECONDARY)
    if col == "half_edge_1":
        ax.yaxis.set_major_locator(mticker.MultipleLocator(0.1))
        ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.1f"))

    plot_df = df[["rho", col, "year"]].dropna().sample(frac=1, random_state=42)
    ax.scatter(plot_df["rho"], plot_df[col], s=20, linewidths=0,
        c=[YEAR_COLORS[y] for y in plot_df["year"]], zorder=2)

    for year in years:
        sub = df[df["year"] == year].dropna(subset=["rho", col])
        coeffs = np.polyfit(sub["rho"], sub[col], 1)
        x_fit = np.linspace(sub["rho"].min(), sub["rho"].max(), 300)
        ax.plot(x_fit, np.polyval(coeffs, x_fit),
                color=YEAR_COLORS[year], linewidth=2.0, zorder=3,
                path_effects=[pe.Stroke(linewidth=3.0, foreground="white"), pe.Normal()])

    # data minimum
    col_min = df[col].min()
    ax.axhline(col_min, color=PRIMARY_INK, linewidth=1.2, linestyle="--", zorder=2, alpha=0.8)

    # theoretical minimum - maybe we'll add that later?
    # if col == "half_edge_1":
    #     x_range = np.linspace(plot_df["rho"].min(), plot_df["rho"].max(), 300)
    #     ax.plot(x_range, minimum_capy(x_range), color="purple", linewidth=1.2, linestyle=":", zorder=3)

    return fig, ax


def save_rho_metrics_legend(years, out_dir, prefix):
    """Save the standalone year and reference-line legend."""
    year_handles = [mlines.Line2D([], [], color=YEAR_COLORS[y], marker="o",
                      linestyle="-", linewidth=1.2, markersize=6, label=str(y))
        for y in years]
    fit_handle = mlines.Line2D([], [], color=SECONDARY, linestyle="-", linewidth=2.0, label="linear fit per decade",
                             path_effects=[pe.Stroke(linewidth=3.0, foreground="white"), pe.Normal()])
    min_handle = mlines.Line2D([], [], color=PRIMARY_INK, linestyle="--", linewidth=1.2, label="data minimum")
    # curve_handle = mlines.Line2D([], [], color="purple", linestyle=":", linewidth=1.2, label="theoretical minimum")

    # save legend as a standalone figure
    fig_leg, ax_leg = plt.subplots(figsize=(6, 0.5))
    ax_leg.axis("off")
    ax_leg.legend(handles=year_handles + [fit_handle, min_handle],
        loc="center", ncol=len(years) + 2, frameon=False,
        fontsize=14, labelcolor=SECONDARY, handletextpad=0.4)
    fig_leg.savefig(out_dir / f"{prefix}_legend.png", bbox_inches="tight", dpi=300)
    plt.close(fig_leg)
    print(f"Saved to {out_dir / f'{prefix}_legend.png'}")


def main(
    filename: str = "data/shared/outputs/tracts_in_cbsa/white_black.csv",
    output_dir: str = "",
) -> None:
    plot_metrics_vs_rho(filename, output_dir)


if __name__ == "__main__":
    typer.run(main)
