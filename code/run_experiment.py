"""Prepare numerical experiment results and national figure data without drawing images."""

import argparse
from pathlib import Path

from national_pipeline.derived_file_paths import build_study_area_label
from national_pipeline.pipeline_config import load_configuration

EXPERIMENT_DIRECTORIES = {
    "national": "national/processed_data/history",
    "ranked-population-table": "national/tables/ranked_population_table",
    "score-ranks": "national/processed_data/score_ranks",
    "population-composition": "national/processed_data/population_composition",
    "entropy-by-geography": "national/processed_data/entropy_by_geography",
    "grid-vs-national-scores": "national/processed_data/grid_vs_national_scores",
    "grid-reference-scores": "experiments/grid_configurations/grid_reference_scores",
    "grid-pop-share-arrangements": "experiments/grid_configurations/grid_pop_share_arrangements",
    "grid-score-comparisons": "experiments/grid_configurations/grid_score_comparisons",
    "grid-distributions": "experiments/grid_configurations/distributions",
    "capy-weights": "national/processed_data/capy_weights",
    "triangular": "experiments/reardon_osullivan",
}


def main() -> None:
    """Run selected experiments in argument order, stopping if any experiment fails."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="Experiments run in the supplied order. Options apply to the selected workflows that use them.",
    )
    parser.add_argument("experiments", nargs="+", choices=EXPERIMENT_DIRECTORIES)
    parser.add_argument("--config", type=Path, help="YAML configuration for national inputs")
    parser.add_argument(
        "--data-directory",
        type=Path,
        default=Path("results"),
        help="Result root, relative to the repository unless absolute (default: results)",
    )
    parser.add_argument("--samples", type=int, default=10000, help="Binary grids per class")
    parser.add_argument(
        "--seed",
        type=int,
        default=20260918,
        help="Random seed for grid-pop-share-arrangements, grid-score-comparisons, grid-distributions",
    )
    arguments = parser.parse_args()

    repository_root = Path(__file__).resolve().parent.parent

    for experiment_name in arguments.experiments:
        data_directory = (
            repository_root / arguments.data_directory / EXPERIMENT_DIRECTORIES[experiment_name]
        )

        if experiment_name == "national":
            from national_figures.prepare_national_results import prepare_national_figure_data

            config = load_configuration(
                arguments.config or repository_root / "code/configs/replication.yaml"
            )
            selection_folder = build_study_area_label(config)

            prepare_national_figure_data(config, repository_root, data_directory / selection_folder)

        elif experiment_name == "entropy-by-geography":
            from national_figures.prepare_entropy_by_geography import prepare_entropy_data

            config = load_configuration(
                arguments.config or repository_root / "code/configs/replication.yaml"
            )
            selection_folder = f"WB_{build_study_area_label(config)}"

            prepare_entropy_data(config, repository_root, data_directory / selection_folder)

        elif experiment_name == "grid-vs-national-scores":
            from national_figures.prepare_grid_vs_national_scores import (
                prepare_grid_vs_national_scores,
            )

            config = load_configuration(
                arguments.config or repository_root / "code/configs/replication.yaml"
            )
            selection_folder = build_study_area_label(config)

            prepare_grid_vs_national_scores(
                config, repository_root, data_directory / selection_folder
            )

        elif experiment_name == "population-composition":
            from national_figures.prepare_population_composition import (
                prepare_population_composition_data,
            )

            config = load_configuration(
                arguments.config or repository_root / "code/configs/replication.yaml"
            )
            selection_folder = build_study_area_label(config)

            prepare_population_composition_data(
                config, repository_root, data_directory / selection_folder
            )

        elif experiment_name == "score-ranks":
            from national_figures.prepare_score_ranks import prepare_score_rank_data

            config = load_configuration(
                arguments.config or repository_root / "code/configs/replication.yaml"
            )
            selection_folder = build_study_area_label(config)

            table_directory = (
                repository_root / arguments.data_directory / "national/tables/score_ranks"
            )
            prepare_score_rank_data(
                config,
                repository_root,
                data_directory / selection_folder,
                table_directory / selection_folder,
            )

        elif experiment_name == "ranked-population-table":
            from national_figures.prepare_ranked_table import prepare_ranked_population_table

            config = load_configuration(
                arguments.config or repository_root / "code/configs/replication.yaml"
            )
            selection_folder = build_study_area_label(config)

            prepare_ranked_population_table(
                config, repository_root, data_directory / selection_folder
            )

        elif experiment_name == "grid-reference-scores":
            from experiments.grid_configurations.grid_reference_scores import (
                save_grid_reference_scores,
            )

            save_grid_reference_scores(data_directory)

        elif experiment_name == "grid-pop-share-arrangements":
            from experiments.grid_configurations.grid_pop_share_arrangements import (
                run_grid_pop_share_arrangements,
            )

            run_grid_pop_share_arrangements(data_directory, arguments.seed)

        elif experiment_name == "grid-score-comparisons":
            from experiments.grid_configurations.grid_score_comparisons import (
                run_grid_score_comparisons,
            )

            run_grid_score_comparisons(data_directory, arguments.seed)

        elif experiment_name == "grid-distributions":
            from experiments.grid_configurations.grid_distributions import run_grid_distributions

            run_grid_distributions(data_directory, arguments.samples, arguments.seed)

        elif experiment_name == "capy-weights":
            from national_figures.compare_capy_weights import run_capy_weight_comparison

            config = load_configuration(
                arguments.config or repository_root / "code/configs/replication.yaml"
            )

            selection_folder = build_study_area_label(config)

            data_directory /= selection_folder

            run_capy_weight_comparison(config, repository_root, data_directory)

        elif experiment_name == "triangular":
            from experiments.reardon_osullivan.triangular_lattices import run_triangular_lattices

            run_triangular_lattices(data_directory)


if __name__ == "__main__":
    main()
