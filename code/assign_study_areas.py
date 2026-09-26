"""Build configured study-area definitions and select Census units for graph construction."""

import argparse
from pathlib import Path

from capy_core.assign_study_areas.run_assignment import assign_study_areas
from capy_core.assign_study_areas.study_area_columns import MembershipColumn
from capy_core.pipeline_config import load_configuration


def main() -> int:
    """Run study-area assignment, returning zero only after all selected outputs succeed.

    Returns:
        int: Zero after definitions, memberships, and their accounting are written.

    Raises:
        SystemExit: Configuration, missing inputs, or failed checks prevent completion.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()

    try:
        config = load_configuration(args.config)
        summary_df = assign_study_areas(config, Path(__file__).resolve().parents[1])
    except (ValueError, OSError) as error:
        parser.exit(1, f"Study-area assignment could not complete: {error}\n")

    print(f"Study-area assignment complete: {len(summary_df)} area/year/level outcomes.")
    print(summary_df[MembershipColumn.STATUS].value_counts().to_string())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
