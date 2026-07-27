"""Compare consecutive decades of observed Black population cluster metrics."""

from pathlib import Path
import pandas as pd

EXPERIMENT_DIR = Path(__file__).resolve().parent.parent
print(f"Experiment directory: {EXPERIMENT_DIR}")
INPUT = EXPERIMENT_DIR / "data" / "cluster_metrics.csv"
OUTPUT = EXPERIMENT_DIR / "data" / "cluster_changes.csv"
mass_tolerance = 0.05  # fraction of previous decade's mass that is considered "stable"


def calculate_changes(metrics: pd.DataFrame, mass_tolerance: float = 0.05):
    rows = []
    for (cbsa, cluster), group in metrics.groupby(["cbsa", "cluster"], sort=True):
        group = group.sort_values("year")
        records = list(group.to_dict("records"))
        for previous, current in zip(records, records[1:]):
            print(f"Comparing {previous['year']} to {current['year']} of {cbsa} {cluster}")
            mass_change = current["area_black_population"] - previous["area_black_population"]
            mass_change_fraction = mass_change / previous["area_black_population"] if previous["area_black_population"] != 0 else float("nan")
            spread_change = current["spread"] - previous["spread"]
            spread_change_fraction = (spread_change / previous["spread"] if previous["spread"] != 0 
                                      else float("nan"))
            mass_stable = abs(mass_change_fraction) <= mass_tolerance

            if spread_change > 0 and mass_stable:
                change_type = "diffusion_with_no_mass_change"
            elif spread_change > 0 and mass_change_fraction < -mass_tolerance:
                change_type = "diffusion_with_mass_loss"
            elif spread_change > 0:
                change_type = "expansion_with_mass_growth"
            elif spread_change < 0:
                change_type = "concentration"
            else:
                change_type = "no_spread_change"

            rows.append({"cbsa": cbsa,
                    "cluster": cluster,
                    "from_year": previous["year"],
                    "to_year": current["year"],
                    "from_center_gisjoin": previous["center_gisjoin"],
                    "to_center_gisjoin": current["center_gisjoin"],
                    "from_area_black_population": previous["area_black_population"],
                    "to_area_black_population": current["area_black_population"],
                    "mass_change": mass_change,
                    "mass_change_fraction": mass_change_fraction,
                    "mass_stable": mass_stable,
                    "from_spread": previous["spread"],
                    "to_spread": current["spread"],
                    "spread_change_edges": spread_change,
                    "spread_change_fraction": spread_change_fraction,
                    "diffusion": change_type.startswith("diffusion"),
                    "change_type": change_type})
    return pd.DataFrame(rows)


metrics = pd.read_csv(INPUT, dtype={"cbsa": str, "cluster": str, "center_gisjoin": str})
changes = calculate_changes(metrics, mass_tolerance=mass_tolerance)
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
changes.to_csv(OUTPUT, index=False)
print(f"Wrote {len(changes)} decade comparisons to {OUTPUT}")