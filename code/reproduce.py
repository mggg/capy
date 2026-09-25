"""Run the implemented stages of the Capy replication pipeline."""

import argparse
from pathlib import Path

from capy_core.pipeline_config import load_configuration
from capy_core.retrieve_data.retrieve_files import retrieve_raw_data


def main() -> int:
    """Run raw-data retrieval and report whether every selected file is ready.

    Returns:
        int: Zero when complete, or one when a selected file failed or is pending.

    Raises:
        SystemExit: Argument parsing requests exit, or invalid inputs prevent retrieval.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use files in the configured folders without downloading, overriding the configuration",
    )
    args = parser.parse_args()

    repository = Path(__file__).resolve().parents[1]
    try:
        config = load_configuration(args.config)

        if args.offline:
            config.offline = True

        result = retrieve_raw_data(config, repository)
    except (ValueError, OSError) as error:
        parser.exit(1, f"Retrieval could not complete: {error}\n")

    status = "complete" if result.complete else "incomplete"
    print(f"Retrieval {status}: {len(result.file_results)} requested files")
    return 0 if result.complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
