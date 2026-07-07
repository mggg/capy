from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
import typer

try:
    from .parse_output import enrich_metrics
except ImportError:
    from parse_output import enrich_metrics


METRICS = ["e_assort",
            "he_assort",
            "skew_self_0",
            "skew_other_0",
            "edge_0",
            "skew'_self_0",	
            "skew'_other_0",
            "half_edge_0",
            "skew_self_exact_0",
            "skew_other_exact_0",
            "edge_exact_0",	
            "skew'_self_exact_0",
            "skew'_other_exact_0",
            "half_edge_exact_0",	
            "skew_self_0.5",	
            "skew_other_0.5",	
            "edge_0.5",
            "skew'_self_0.5",
            "skew'_other_0.5",	
            "half_edge_0.5",
            "skew_self_exact_0.5",
            "skew_other_exact_0.5",	
            "edge_exact_0.5",	
            "skew'_self_exact_0.5",
            "skew'_other_exact_0.5",
            "half_edge_exact_0.5",
            "skew_self_1",
            "skew_other_1",
            "edge_1",
            "skew'_self_1",
            "skew'_other_1",
            "half_edge_1",
            "skew_self_exact_1",
            "skew_other_exact_1",
            "edge_exact_1",
            "skew'_self_exact_1",
            "skew'_other_exact_1",
            "half_edge_exact_1",
            "skew_self_2",
            "skew_other_2",
            "edge_2",
            "skew'_self_2",
            "skew'_other_2",
            "half_edge_2",
            "skew_self_exact_2",
            "skew_other_exact_2",
            "edge_exact_2",
            "skew'_self_exact_2",
            "skew'_other_exact_2",
            "half_edge_exact_2",
            "skew_self_10",
            "skew_other_10",
            "edge_10",
            "skew'_self_10",
            "skew'_other_10",
            "half_edge_10",
            "skew_self_exact_10",
            "skew_other_exact_10",
            "edge_exact_10",
            "skew'_self_exact_10",
            "skew'_other_exact_10",
            "half_edge_exact_10",
            "skew_self_lim",
            "skew_other_lim",
            "edge_lim",
            "skew'_self_lim",
            "skew'_other_lim",
            "half_edge_lim",	
            "skew_self_exact_lim",
            "skew_other_exact_lim",	
            "edge_exact_lim",
            "skew'_self_exact_lim",
            "skew'_other_exact_lim",
            "half_edge_exact_lim",
            "dissimilarity_1",
            "dissimilarity_2",	
            "dissimilarity_10",	
            "frey",	
            "gini",	
            "moran_A",	
            "moran_P",	
            "moran_L",
            "moran_M",
            "moran_D_1",
            "moran_D_2"
            "moran_A_white",	
            "moran_P_white",	
            "moran_L_white",
            "moran_M_white",
            "moran_D_1_white",
            "moran_D_2_white"
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
