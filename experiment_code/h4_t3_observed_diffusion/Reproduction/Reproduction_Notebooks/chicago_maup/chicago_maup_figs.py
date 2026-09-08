import pandas as pd
import numpy as np
import geopandas as gpd
import matplotlib.pyplot as plt
import gerrychain
import plotly.express as px
pd.set_option('display.max_columns', None)
import os
os.chdir("/Users/samstephenson/Downloads/capy-bara")

tract= pd.read_csv("outputs/tracts_in_cbsa/white_black.csv")
tract["year"] = tract["filename"].str.extract(r"(\d{4})").astype(int)
tract["cbsa_code"] = (
    tract["filename"]
      .str.extract(rf"tracts_in_cbsa_(\d+)")[0]
      .astype(int)
)

bg = pd.read_csv("outputs/block_groups_in_cbsa/white_black.csv")
bg["year"] = bg["filename"].str.extract(r"(\d{4})").astype(int)
bg["cbsa_code"] = (
    bg["filename"]
      .str.extract(rf"block_groups_in_cbsa_(\d+)")[0]
      .astype(int)
)
block = pd.read_csv("outputs/blocks_in_cbsa/white_black.csv")
block["year"] = block["filename"].str.extract(r"(\d{4})").astype(int)
block["cbsa_code"] = (
    block["filename"]
      .str.extract(rf"blocks_in_cbsa_(\d+)")[0]
      .astype(int)
)

tract = tract[(tract["year"] == 2020) & (tract["cbsa_code"] == 16980)]
block = block[(block["year"] == 2020) & (block["cbsa_code"] == 16980)]
bg = bg[(bg["year"] == 2020) & (bg["cbsa_code"] == 16980)]

metrics = [
    "Capy",
    "dissimilarity",
    "Moran_P"]


bg_values = [
    bg["half_edge_1"].iloc[0],
    bg["dissimilarity_1"].iloc[0],
    bg["moran_P"].iloc[0]]

tract_values = [
    tract["half_edge_1"].iloc[0],
    tract["dissimilarity_1"].iloc[0],
    tract["moran_P"].iloc[0]
    ]

block_values = [
    block["half_edge_1"].iloc[0],
    block["dissimilarity_1"].iloc[0],
    block["moran_P"].iloc[0]
    ]

x = np.arange(len(metrics))
width = 0.1

fig, ax = plt.subplots(figsize=(8, 5))

ax.bar(x + width, tract_values, width, label="Tracts")
ax.bar(x, bg_values, width, label="Block Groups")
ax.bar(x-width, block_values, width, label="Blocks")


ax.set_xticks(x)
ax.set_xticklabels(metrics, rotation=20, ha="right")
ax.set_ylabel("Metric Value")
ax.set_title("MAUP_2020-Black vs White")
ax.legend()

plt.tight_layout()
plt.savefig("Reproduction/Reproduction_Figures/chicago_maup/chicago_maup_viz.png")