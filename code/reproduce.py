"""Run the implemented stages of the Capy replication pipeline."""

import argparse
from pathlib import Path

from capy_core.assign_study_areas.run_assignment import assign_study_areas
from capy_core.assign_study_areas.study_area_columns import MembershipColumn
from capy_core.join_geographies.join_tables import join_geography_tables
from capy_core.pipeline_config import load_configuration
from capy_core.process_population.process_tables import process_population_tables
from capy_core.retrieve_data.retrieve_files import retrieve_raw_data

PIPELINE_STAGES = (
    "retrieve",
    "process-population",
    "join-geographies",
    "assign-study-areas",
)


def build_argument_parser() -> argparse.ArgumentParser:
    """Describe configuration, positional stage selection, and the retrieval-only offline override."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Available stages, in execution order:\n"
            "  retrieve             Download or reuse the selected raw inputs.\n"
            "  process-population   Check population counts and save population tables.\n"
            "  join-geographies     Join boundaries to processed population tables.\n"
            "  assign-study-areas   Define study areas and select their Census units.\n\n"
            "Selected stages run once in pipeline order. Unselected prerequisites are not run.\n"
            "Omit stages to run all four. A failed or incomplete stage stops the pipeline."
        ),
    )
    parser.add_argument("--config", type=Path, required=True, help="YAML run configuration")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="During retrieval, reuse local files without downloading; overrides the configuration",
    )
    parser.add_argument(
        "stages", nargs="*", metavar="STAGE", help="Stages to run (default: all stages)"
    )

    return parser


def main() -> int:
    """Run selected stages in pipeline order, stopping on failure or incomplete retrieval.

    Each selected stage runs once. With no stage names, run every implemented stage; otherwise
    use existing inputs for unselected prerequisites. Summaries retain each stage's accounting.
    ValueError and OSError become command-line failures; other reader exceptions propagate.

    Returns:
        int: Zero after all selected stages complete, or one if retrieval is incomplete.

    Raises:
        SystemExit: Argument parsing requests exit, or configuration or stage inputs are invalid.
    """
    parser = build_argument_parser()
    args = parser.parse_args()
    unknown_stages = set(args.stages) - set(PIPELINE_STAGES)

    if unknown_stages:
        parser.error(f"Unknown stages: {', '.join(sorted(unknown_stages))}")

    selected_stages = args.stages or PIPELINE_STAGES
    repository = Path(__file__).resolve().parents[1]
    operation = "Configuration loading"

    try:
        config = load_configuration(args.config)

        if args.offline:
            config.offline = True

        if "retrieve" in selected_stages:
            operation = "Retrieval"
            result = retrieve_raw_data(config, repository)
            status = "complete" if result.complete else "incomplete"
            print(f"Retrieval {status}: {len(result.file_results)} requested files")

            if not result.complete:
                return 1

        if "process-population" in selected_stages:
            operation = "Population processing"
            summaries = process_population_tables(config, repository)
            print(f"Population processing complete: {len(summaries)} tables saved")

        if "join-geographies" in selected_stages:
            operation = "Geographic joining"
            join_geography_tables(config, repository)
            print("Geographic joining complete. See join_summary.csv for population accounting.")

        if "assign-study-areas" in selected_stages:
            operation = "Study-area assignment"
            summary_df = assign_study_areas(config, repository)
            print(f"Study-area assignment complete: {len(summary_df)} area/year/level outcomes.")
            print(summary_df[MembershipColumn.STATUS].value_counts().to_string())
    except (ValueError, OSError) as error:
        parser.exit(1, f"{operation} could not complete: {error}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
