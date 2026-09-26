"""Process downloaded Census and NHGIS population tables without starting any downloads."""

import argparse
from pathlib import Path

from capy_core.pipeline_config import load_configuration
from capy_core.process_population.process_tables import process_population_tables


def main() -> int:
    """Run population processing with a YAML configuration and report the number of saved tables.

    Returns:
        int: Zero after every selected table passes its checks and is saved.

    Raises:
        SystemExit: Invalid settings, missing inputs, or failed checks prevent completion.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()

    repository = Path(__file__).resolve().parents[1]

    try:
        config = load_configuration(args.config)
        summaries = process_population_tables(config, repository)
    except (ValueError, OSError) as error:
        parser.exit(1, f"Population processing could not complete: {error}\n")

    print(f"Population processing complete: {len(summaries)} tables saved")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
