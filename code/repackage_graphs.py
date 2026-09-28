"""Repackage existing graph ZIPs into numbered parts without rebuilding graphs or metrics."""

import argparse
from pathlib import Path

from capy_core.build_graphs.repackage_archives import repackage_graph_archives
from capy_core.pipeline_config import load_configuration


def main() -> None:
    """Read the run's graph selections and repackage only archives that already exist."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    config = load_configuration(args.config)
    repository_root = Path(__file__).resolve().parents[1]
    repackage_graph_archives(config, repository_root)


if __name__ == "__main__":
    main()
