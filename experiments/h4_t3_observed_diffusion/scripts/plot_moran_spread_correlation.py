import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
import pandas as pd
from pathlib import Path

EXPERIMENT_DIR = Path(__file__).resolve().parent.parent
DIFFUSION_METRIC = 'euclidean_spread' #other options include 'core_spread', 'core_euclidean_spread', or 'euclidean_spread'


df = pd.read_csv(EXPERIMENT_DIR / "data" / "auto_cluster_metrics.csv")
buf0 = df[df['buffer_size'] == 0].copy()

print(len(df))
print(len(buf0))

buffer_sizes = sorted(df['buffer_size'].unique())
cmap_buf = plt.cm.viridis
norm_buf = mcolors.Normalize(vmin=min(buffer_sizes), vmax=max(buffer_sizes))

fig, ax = plt.subplots(figsize=(8, 6))

ax.scatter(df[DIFFUSION_METRIC], df['moran'],
           c=df['buffer_size'], cmap=cmap_buf, norm=norm_buf,
           s=25, alpha=0.7, linewidths=0)

m_all, b_all = np.polyfit(df[DIFFUSION_METRIC], df['moran'], 1)
x_all = np.linspace(df[DIFFUSION_METRIC].min(), df[DIFFUSION_METRIC].max(), 100)

m_b0, b_b0 = np.polyfit(buf0[DIFFUSION_METRIC], buf0['moran'], 1)
x_b0 = np.linspace(buf0[DIFFUSION_METRIC].min(), buf0[DIFFUSION_METRIC].max(), 100)

buf5 = df[df['buffer_size'] == 5].copy()
m_b5, b_b5 = np.polyfit(buf5[DIFFUSION_METRIC], buf5['moran'], 1)
x_b5 = np.linspace(buf5[DIFFUSION_METRIC].min(), buf5[DIFFUSION_METRIC].max(), 100)

buf10 = df[df['buffer_size'] == 10].copy()
m_b10, b_b10 = np.polyfit(buf10[DIFFUSION_METRIC], buf10['moran'], 1)
x_b10 = np.linspace(buf10[DIFFUSION_METRIC].min(), buf10[DIFFUSION_METRIC].max(), 100)


r_all = df["moran"].corr(df[DIFFUSION_METRIC])
ax.plot(x_all, m_all * x_all + b_all, color='black', linewidth=1.5,
        label=f'All buffers; r={r_all:.2f}, R²={r_all**2:.2f}')

r_b0 = buf0["moran"].corr(buf0[DIFFUSION_METRIC])
ax.plot(x_b0, m_b0 * x_b0 + b_b0, color='tomato', linewidth=1.5, linestyle='--',
        label=f'Buffer = 0 only; r={r_b0:.2f}, R²={r_b0**2:.2f}')

r_b5 = buf5["moran"].corr(buf5[DIFFUSION_METRIC])
ax.plot(x_b5, m_b5 * x_b5 + b_b5, color='blue', linewidth=1.5, linestyle='--',
        label=f'Buffer = 5 only; r={r_b5:.2f}, R²={r_b5**2:.2f}')

r_b10 = buf10["moran"].corr(buf10[DIFFUSION_METRIC])
ax.plot(x_b10, m_b10 * x_b10 + b_b10, color='orange', linewidth=1.5, linestyle='--',
        label=f'Buffer = 10 only; r={r_b10:.2f}, R²={r_b10**2:.2f}')

sm = plt.cm.ScalarMappable(norm=norm_buf, cmap=cmap_buf)
fig.colorbar(sm, ax=ax, label='Buffer size', fraction=0.04, pad=0.02)
ax.legend(fontsize=9, frameon=False)
ax.set_xlabel(DIFFUSION_METRIC)
ax.set_ylabel("Moran's I")
ax.set_title(f"Moran vs {DIFFUSION_METRIC} by Buffer Value", fontsize=11)

fig.savefig(EXPERIMENT_DIR / "figures" / f"moran_{DIFFUSION_METRIC}_correlation.png",
            dpi=200, bbox_inches='tight')
plt.close(fig)
print(f"Saved moran_{DIFFUSION_METRIC}_correlation.png")
