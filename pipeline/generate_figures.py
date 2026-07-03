from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
import typer

try:
    from .parse_output import enrich_metrics
except ImportError:
    from parse_output import enrich_metrics


METRICS = [
    "edge_lam_1_angle_1",
    "half_edge_lam_1_angle_1",
    "edge_lam_1_angle_2",
    "half_edge_lam_1_angle_2",
    "moran",
    "dissimilarity",
    "frey",
    "gini",
]


def ensure_metadata(df: pd.DataFrame) -> pd.DataFrame:
    required = {"definition_month_year", "year", "cbsa_title", "total_population_2020"}
    if required.issubset(df.columns):
        return df
    return enrich_metrics(df)


def main(
    filename: str = "outputs/white_poc_parsed.csv",
    n: int = 10,
    prefix: str = "white_poc",
):
    output_dir = Path(filename).parent / "figures"
    output_dir.mkdir(parents=True, exist_ok=True)

    df = ensure_metadata(pd.read_csv(filename))
    df = df.sort_values("total_population_2020", ascending=False)

    for month_year in set(df["definition_month_year"]):
        month_year_df = df[df["definition_month_year"] == month_year]

        top_n_metros = set(month_year_df["cbsa_title"].drop_duplicates()[:n])
        top_n_df = month_year_df[
            month_year_df["cbsa_title"].apply(lambda x: x in top_n_metros)
        ].sort_values(["cbsa_title", "year"])

        sns.set_theme(rc={"figure.figsize": (10, 4)})
        for metric in METRICS:
            if metric not in top_n_df.columns:
                continue
            ax = sns.lineplot(
                data=top_n_df,
                y=metric,
                x="year",
                hue="cbsa_title",
                legend=True,
            )
            ax.set_xticks(sorted(top_n_df["year"].unique()))
            plt.legend(bbox_to_anchor=(1.05, 1), loc="upper left")
            plt.tight_layout()
            plt.savefig(output_dir / f"{prefix}_{month_year}_{metric}.png")
            plt.close()


if __name__ == "__main__":
    typer.run(main)
