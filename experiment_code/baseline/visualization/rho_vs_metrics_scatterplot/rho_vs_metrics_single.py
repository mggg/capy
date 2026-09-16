"""Creates scatter plots for each metric vs minority share on the tracts in CBSA level in individual files. For consistency with other figures, only CBSAs with population > 100K are included."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))  # project root (for capy_core)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # experiment_code/baseline/ (for visualization)

import matplotlib.lines as mlines
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import typer

from capy_core.process_results import enrich_metrics
from experiment_code.visualization_settings import GRID_COLOR, PRIMARY_INK, SECONDARY, GRID_METRICS


POPULATION_THRESHOLD = 100_000 # only include CBSAs with population > 100K
ALL_YEARS = {1980, 1990, 2000, 2010, 2020}

def main(filename: str = "data/shared/outputs/tracts_in_cbsa/white_black.csv") -> None:
    path_to_file = filename
    CSV = Path(path_to_file)

    df = enrich_metrics(pd.read_csv(CSV))
    if "white_poc" in path_to_file:
        df["rho"] = df["total_poc"] / (df["total_poc"] + df["total_white"])
        prefix = "wpoc"
    elif "white_black" in path_to_file:
        df["rho"] = df["total_black"] / (df["total_black"] + df["total_white"])
        prefix = "wb"
    else:
        raise ValueError("Unknown file type: expected white_poc or white_black in filename")

    YEARS = sorted(df["year"].unique())
    YEAR_COLORS = {1980: '#1560bd', 1990: '#006b3c', 2000: "#8db600", 2010: "#ffa812", 2020: "#d11a42"}

    # select CBSAs present in all 5 decades with population > 100K
    df["area_code"] = df["filename"].str.extract(r"tracts_in_cbsa_(\d+)_")
    has_all_years = df.groupby("area_code")["year"].apply(lambda s: ALL_YEARS.issubset(set(s)))
    cbsas_all_years = has_all_years[has_all_years].index

    min_pop = df.groupby("area_code")["total_population"].min()
    cbsas_large = min_pop[min_pop > POPULATION_THRESHOLD].index
    valid_cbsas = cbsas_all_years.intersection(cbsas_large)
    df = df[df["area_code"].isin(valid_cbsas)]

    PANELS = [
        dict(col="half_edge_1", title="Capy"),
        dict(col="moran_P", title="Moran's I"),
        dict(col="dissimilarity_1", title="Dissimilarity")]

    OUT_DIR = Path("figures") / "baseline" / "tracts_in_cbsa" / "rho_vs_metrics"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    year_handles = [mlines.Line2D([], [], color=YEAR_COLORS[y], marker="o",
                      linestyle="-", linewidth=1.2, markersize=6, label=str(y))
        for y in YEARS]
    fit_handle = mlines.Line2D([], [], color=SECONDARY, linestyle="-", linewidth=1.2, label="linear fit per decade")
    min_handle = mlines.Line2D([], [], color=PRIMARY_INK, linestyle="--", linewidth=1.2, label="data minimum")

    # save legend as a standalone figure
    fig_leg, ax_leg = plt.subplots(figsize=(6, 0.5))
    ax_leg.axis("off")
    ax_leg.legend(handles=year_handles + [fit_handle, min_handle],
        loc="center", ncol=len(YEARS) + 2, frameon=False,
        fontsize=14, labelcolor=SECONDARY, handletextpad=0.4)
    fig_leg.savefig(OUT_DIR / f"{prefix}_legend.png", bbox_inches="tight", dpi=300)
    plt.close(fig_leg)
    print(f"Saved to {OUT_DIR / f'{prefix}_legend.png'}")

    for panel in PANELS:
        col = panel["col"]
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

        for year in YEARS:
            sub = df[df["year"] == year].dropna(subset=["rho", col])
            coeffs = np.polyfit(sub["rho"], sub[col], 1)
            x_fit = np.linspace(sub["rho"].min(), sub["rho"].max(), 300)
            ax.plot(x_fit, np.polyval(coeffs, x_fit),
                    color=YEAR_COLORS[year], linewidth=1.2, zorder=3)

        col_min = df[col].min()
        ax.axhline(col_min, color=PRIMARY_INK, linewidth=1.2, linestyle="--", zorder=2, alpha=0.8)

        out = OUT_DIR / f"{prefix}_{GRID_METRICS[col].split(" ")[0].lower().replace("'", '')}.png"
        fig.savefig(out, dpi=300, bbox_inches="tight")
        plt.close(fig)
        print(f"Saved to {out}")


if __name__ == "__main__":
    typer.run(main)
