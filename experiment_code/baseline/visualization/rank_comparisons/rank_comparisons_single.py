"""Pairwise rank comparison scatterplots, one figure per metric pair.

For each pair of metrics (Capy, Dissimilarity, Moran's I), plots the
top 100 cities (by population) in a given year by their within-group score ranks
against each other.

Saves one PNG per pair to:
    figures/baseline/<node_areas>_in_<study_areas>/rank_comparisons/<stem>_rank_<y>_vs_<x>.png

Usage (run from the project root):
    python experiment_code/baseline/visualization/rank_comparisons/rank_comparisons_single.py
"""

import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4])) # project root
sys.path.insert(0, str(Path(__file__).resolve().parents[2])) # experiment_code/baseline/

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import typer

from experiment_code.visualization_settings import PALETTE, SECONDARY, GRID_COLOR


USED_COLS = {
    "half_edge_1": "Half Edge",
    "dissimilarity_1": "Dissimilarity",
    "moran_P": "Moran's I",
    "filename": "filename",
    "total_population": "total_population"}
DISPLAY_METRICS = {
    "half_edge_1": "Capy Rank",
    "dissimilarity_1": "Dissimilarity Rank",
    "moran_P": "Moran's I Rank"}


def load_ranked_data(filename: str, year: str, top_n: int) -> pd.DataFrame:
    """Load complete observations and rank metrics within the top-population sample."""
    df = pd.read_csv(filename, usecols=list(USED_COLS))
    df["year"] = df["filename"].str.extract(r"(\d{4})")
    df = df.dropna(subset=list(USED_COLS))
    df = df[df["year"] == year]
    df = df.sort_values("total_population", ascending=False).head(top_n)

    for col in DISPLAY_METRICS:
        df[col + "_rank"] = df[col].rank(method="average")

    return df


def plot_rank_comparisons(df: pd.DataFrame, out_dir: Path, stem: str) -> None:
    """Draw and save one rank comparison figure per metric pair."""
    out_dir.mkdir(parents=True, exist_ok=True)

    pairs = list(combinations(DISPLAY_METRICS.keys(), 2))  # 3 pairs

    for x_col, y_col in pairs:
        fig, ax = plt.subplots(figsize=(5, 5))
        ax.spines[["top", "right", "left", "bottom"]].set_visible(False)
        ax.grid(color=GRID_COLOR, linewidth=0.8, zorder=0)
        ax.tick_params(length=0, labelsize=14, labelcolor=SECONDARY)
        ax.set_box_aspect(1)

        x = df[x_col + "_rank"]
        y = df[y_col + "_rank"]

        ax.scatter(x, y, s=18, alpha=1, color=PALETTE[0], linewidths=0, zorder=2)

        # diagonal reference line
        x_line = [x.min(), x.max()]
        ax.plot(x_line, x_line, color=SECONDARY, lw=1, alpha=0.7)

        # spearman correlation
        rho = x.corr(y, method="spearman")
        # ax.annotate(f"Spearman ρ = {rho:.2f}", xy=(0.05, 0.95), xycoords="axes fraction", fontsize=14,
        #             ha="left", va="top", color=SECONDARY)

        if "half_edge" in x_col:
            x_col = "capy"
        rho = round(rho, 2).astype(str).replace(".", "p") # for filename

        out_path = out_dir / f"{stem}_rank_{y_col.split('_')[0]}_vs_{x_col.split('_')[0]}_corr{rho}.png"
        fig.savefig(out_path, dpi=300, bbox_inches="tight")
        plt.close(fig)
        print(f"Saved to {out_path}")


def main(
    filename: str = "data/shared/outputs/tracts_in_cbsa/white_black.csv",
    year: str = "2020", top_n: int = 100) -> None:
    CSV = Path(filename)

    stem = CSV.stem # e.g. "white_black"
    # groups_compared = "White and Black" if stem == "white_black" else "White and POC"

    node_areas, separator, study_areas_key = CSV.parent.name.partition("_in_")
    if not separator or not node_areas or not study_areas_key:
        raise ValueError(
            f"Expected CSV inside a '<geography>_in_<study_area>' directory: {CSV}")
    # study_areas = (
    #     "the largest city per metropolitan area"
    #     if study_areas_key == "max_city"
    #     else study_areas_key)

    df = load_ranked_data(filename, year, top_n)
    out_dir = (Path("figures") / "baseline" / f"{node_areas}_in_{study_areas_key}" / "rank_comparisons")
    plot_rank_comparisons(df, out_dir, stem)


if __name__ == "__main__":
    typer.run(main)
