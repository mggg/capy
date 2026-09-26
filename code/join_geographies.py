"""Join downloaded boundaries to processed population tables and report geographic exclusions."""

import argparse
from pathlib import Path

from capy_core.join_geographies.join_tables import join_geography_tables
from capy_core.pipeline_config import load_configuration


def main() -> int:
    """Run configured geography joins, returning zero after all selected state outputs are saved.

    ValueError and OSError become command-line failure messages. Other exceptions from ZIP,
    geospatial, or Parquet readers propagate with their original tracebacks.

    Returns:
        int: Zero after all selected outputs and the run summary are saved.

    Raises:
        SystemExit: Invalid settings, missing inputs, or failed geography/population checks.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()

    try:
        config = load_configuration(args.config)
        join_geography_tables(config, Path(__file__).resolve().parents[1])
    except (ValueError, OSError) as error:
        parser.exit(1, f"Geographic joining could not complete: {error}\n")

    print("Geographic joining complete. See join_summary.csv for population accounting.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
