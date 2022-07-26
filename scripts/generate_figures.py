import seaborn as sns
import typer
import matplotlib.pyplot as plt
import pandas as pd


def main(
    filename: str = "outputs/white_poc_parsed.csv",
    n: int = 10,
    prefix: str = "white_poc",
):
    df = pd.read_csv(filename)
    df = df.sort_values("total_population_2020", ascending=False)

    for month_year in set(df["definition_month_year"]):
        month_year_df = df[df["definition_month_year"] == month_year]

        top_n_metros = set(month_year_df["cbsa_title"].drop_duplicates()[:n])
        top_n_df = month_year_df[
            month_year_df["cbsa_title"].apply(lambda x: x in top_n_metros)
        ]

        for metric in [
            "edge_lam_1_angle_1",
            "half_edge_lam_1_angle_1",
            "edge_lam_1_angle_2",
            "half_edge_lam_1_angle_2",
            "moran",
            "dissimilarity",
            "frey",
            "gini",
        ]:
            sns.lineplot(
                data=top_n_df, y=metric, x="year", hue="cbsa_title", legend=False
            )
            plt.savefig(f"figures/{prefix}_{month_year}_{metric}.png")
            plt.close()


if __name__ == "__main__":
    typer.run(main)
