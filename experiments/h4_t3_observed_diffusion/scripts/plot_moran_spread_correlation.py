import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
import pandas as pd
from pathlib import Path

EXPERIMENT_DIR = Path(__file__).resolve().parent.parent

df = pd.read_csv(EXPERIMENT_DIR / "data" / "auto_cluster_metrics.csv")
buf0 = df[df['buffer_size'] == 0].copy()

print(len(df))
print(len(buf0))

buffer_sizes = sorted(df['buffer_size'].unique())
cmap_buf = plt.cm.viridis
norm_buf = mcolors.Normalize(vmin=min(buffer_sizes), vmax=max(buffer_sizes))

fig, ax = plt.subplots(figsize=(8, 6))

ax.scatter(df['spread'], df['moran'],
           c=df['buffer_size'], cmap=cmap_buf, norm=norm_buf,
           s=25, alpha=0.7, linewidths=0)

m_all, b_all = np.polyfit(df['spread'], df['moran'], 1)
x_all = np.linspace(df['spread'].min(), df['spread'].max(), 100)
ax.plot(x_all, m_all * x_all + b_all, color='black', linewidth=1.5,
        label=f'All buffers; Pearson corr = {df["moran"].corr(df["spread"]):.2f}')

m_b0, b_b0 = np.polyfit(buf0['spread'], buf0['moran'], 1)
x_b0 = np.linspace(buf0['spread'].min(), buf0['spread'].max(), 100)
ax.plot(x_b0, m_b0 * x_b0 + b_b0, color='tomato', linewidth=1.5, linestyle='--',
        label=f'Buffer = 0 only; Pearson corr = {buf0["moran"].corr(buf0["spread"]):.2f}')

sm = plt.cm.ScalarMappable(norm=norm_buf, cmap=cmap_buf)
fig.colorbar(sm, ax=ax, label='Buffer size', fraction=0.04, pad=0.02)
ax.legend(fontsize=9, frameon=False)
ax.set_xlabel("Spread")
ax.set_ylabel("Moran's I")
ax.set_title("Moran vs Spread by buffer value", fontsize=11)

fig.savefig(EXPERIMENT_DIR / "figures" / "moran_spread_correlation.png",
            dpi=200, bbox_inches='tight')
plt.close(fig)
print("Saved moran_spread_correlation.png")
