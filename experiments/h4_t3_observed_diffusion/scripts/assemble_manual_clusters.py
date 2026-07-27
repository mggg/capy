"""
Assemble manual cluster tract selections into a single CSV compatible with
candidate_tracts.csv for use by calculate_metrics.py and plot_centroids.py.

Reads all CSVs from data/manual_clusters/, parses city/year/cluster from
filenames, and outputs data/manual_cluster_tracts.csv with the columns those scripts need:
  cbsa, year, cluster, gisjoin, geoid, statefp, countyfp,
  black_population, total_population, black_share

Note: centroid_x/centroid_y are not included because the scripts read those
from the dual graph node attributes, not from candidate_tracts.csv.
"""

from pathlib import Path
import pandas as pd

EXPERIMENT_DIR = Path(__file__).resolve().parent.parent
INPUT_DIR = EXPERIMENT_DIR / "data" / "manual_clusters"
OUTPUT = EXPERIMENT_DIR / "data" / "manual_cluster_tracts.csv"

CBSA_BY_CITY = {"chicago": "16980", "philadelphia": "37980"}

rows = []
for csv_path in sorted(INPUT_DIR.glob("*.csv")):
    parts = csv_path.stem.split("_")
    # filename pattern: <city>_<year>_<cluster_name...>
    # year is always a 4-digit number; find its index to split city and cluster
    year_idx = next(i for i, p in enumerate(parts) if p.isdigit() and len(p) == 4)
    city = "_".join(parts[:year_idx])
    year = int(parts[year_idx])
    cluster = "_".join(parts[year_idx + 1:])

    cbsa = CBSA_BY_CITY.get(city)
    if cbsa is None:
        raise ValueError(f"No CBSA mapping for city '{city}' (file: {csv_path.name}). Add it to CBSA_BY_CITY.")

    df = pd.read_csv(csv_path, dtype=str)

    # All census-year exports consistently include these columns
    missing = [c for c in ("GISJOIN", "BLACK", "TOTPOP", "GEOID", "STATEFP", "COUNTYFP", "WHITE") if c not in df.columns]
    if missing:
        raise ValueError(f"{csv_path.name} is missing expected columns: {missing}")

    zero_pop = df[pd.to_numeric(df["WHITE"], errors="coerce").fillna(0) +
                  pd.to_numeric(df["BLACK"], errors="coerce").fillna(0) == 0]
    if not zero_pop.empty:
        print(f"  Warning: dropping {len(zero_pop)} tract(s) with WHITE + BLACK == 0 "
              f"from {csv_path.name}: {zero_pop['GISJOIN'].tolist()}")
        df = df.drop(zero_pop.index)

    df = df.rename(columns={
        "GISJOIN": "gisjoin",
        "GEOID": "geoid",
        "STATEFP": "statefp",
        "COUNTYFP": "countyfp",
        "BLACK": "black_population",
        "TOTPOP": "total_population"})[["gisjoin", "geoid", "statefp", "countyfp", "black_population", "total_population"]]

    df["black_population"] = pd.to_numeric(df["black_population"])
    df["total_population"] = pd.to_numeric(df["total_population"])
    df["black_share"] = df["black_population"] / df["total_population"]

    # Add the CBSA, year, and cluster columns to the front of the df
    df.insert(0, "cbsa", cbsa)
    df.insert(1, "year", year)
    df.insert(2, "cluster", cluster)
    rows.append(df)
    print(f"{csv_path.name}: {len(df)} tracts (cbsa={cbsa}, year={year}, cluster={cluster})")

result = pd.concat(rows, ignore_index=True)
result = result.sort_values(["cbsa", "cluster", "year", "gisjoin"]).reset_index(drop=True)
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
result.to_csv(OUTPUT, index=False)
print(f"\nWrote {len(result)} tract-rows across {len(rows)} cluster-years to {OUTPUT}")
