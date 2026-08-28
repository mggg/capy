import matplotlib.pyplot as plt
import pandas as pd
from pathlib import Path

EXPERIMENT_DIR = Path(__file__).resolve().parent.parent

SHOW_BUFFERS = [0, 1, 3, 7, 10]

df = pd.read_csv(EXPERIMENT_DIR / "data" / "auto_cluster_metrics.csv")
years = sorted(df['year'].unique())

moran_min, moran_max = df['moran'].min(), df['moran'].max()
spread_min, spread_max = df['spread'].min(), df['spread'].max()

for (area_code, city_name, cluster), grp in df.groupby(['area_code', 'city_name', 'cluster'], sort=True):
    print(f"Plotting {city_name}, {cluster}")

    fig, axes = plt.subplots(len(SHOW_BUFFERS), 1, figsize=(7, 3 * len(SHOW_BUFFERS)), sharex=True)

    for ax, buf in zip(axes, SHOW_BUFFERS):
        data = grp[grp['buffer_size'] == buf].sort_values('year')
        axt = ax.twinx()

        ax.plot(data['year'], data['moran'], color='steelblue', marker='o', markersize=4, linewidth=1.5)
        axt.plot(data['year'], data['spread'], color='darkorange', marker='s', markersize=4,
                 linewidth=1.5, linestyle='--')

        ax.set_ylim(moran_min, moran_max)
        axt.set_ylim(spread_min, spread_max)
        ax.set_ylabel("Moran's I", color='steelblue', fontsize=8)
        ax.tick_params(axis='y', labelcolor='steelblue', labelsize=7)
        axt.set_ylabel("Spread", color='darkorange', fontsize=8)
        axt.tick_params(axis='y', labelcolor='darkorange', labelsize=7)
        ax.text(0.01, 0.88, f"Buffer {buf}", transform=ax.transAxes, fontsize=8)
        ax.spines['top'].set_visible(False)
        axt.spines['top'].set_visible(False)

    axes[-1].set_xticks(years)
    axes[-1].set_xticklabels([str(y) for y in years], fontsize=8)
    axes[-1].set_xlabel("Year")

    fig.suptitle(f"{city_name} — {cluster}", fontsize=11)
    fig.tight_layout()

    figure_path = EXPERIMENT_DIR / "figures" / f"{city_name}_{cluster}_moran_spread_by_buffer.png"
    figure_path.parent.mkdir(exist_ok=True)
    fig.savefig(figure_path, dpi=200, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved {figure_path}")
