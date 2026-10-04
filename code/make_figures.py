"""Draw separate PNG figures and legends from saved results, without running experiments."""

import argparse
from pathlib import Path

from national_pipeline.derived_file_paths import build_study_area_label
from national_pipeline.pipeline_config import load_configuration

FIGURE_DIRECTORIES = {
    "national": ("national/processed_data/history", "national"),
    "score-ranks": ("national/processed_data/score_ranks", "national"),
    "population-composition": ("national/processed_data/population_composition", "national"),
    "capy-weights": ("national/processed_data/capy_weights", "national"),
    "grid-distributions": (
        "experiments/grid_configurations/distributions",
        "grid_configurations/distributions",
    ),
    "triangular": ("experiments/reardon_osullivan", "grid_configurations/reardon_osullivan"),
    "entropy-by-geography": ("national/processed_data/entropy_by_geography", "national"),
    "grid-vs-national-scores": ("national/processed_data/grid_vs_national_scores", "national"),
    "grid-reference-scores": (
        "experiments/grid_configurations/grid_reference_scores",
        "grid_configurations/grid_reference_scores",
    ),
    "grid-pop-share-arrangements": (
        "experiments/grid_configurations/grid_pop_share_arrangements",
        "grid_configurations/grid_pop_share_arrangements",
    ),
    "grid-score-comparisons": (
        "experiments/grid_configurations/grid_score_comparisons",
        "grid_configurations/grid_score_comparisons",
    ),
}


def main() -> None:
    """Draw selected image sets in argument order; an input or rendering failure stops the run."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="Workflows run in the supplied order. Shared options apply to every selected workflow.",
    )
    parser.add_argument("figures", nargs="+", choices=FIGURE_DIRECTORIES)
    parser.add_argument("--config", type=Path, help="YAML configuration for national inputs")
    parser.add_argument(
        "--data-directory",
        type=Path,
        default=Path("results"),
        help="Result root, relative to the repository unless absolute (default: results)",
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path("figures"),
        help="Figure root, relative to the repository unless absolute (default: figures)",
    )
    arguments = parser.parse_args()
    repository_root = Path(__file__).resolve().parent.parent

    for figure_name in arguments.figures:
        result_subdirectory, figure_subdirectory = FIGURE_DIRECTORIES[figure_name]
        data_directory = repository_root / arguments.data_directory / result_subdirectory
        output_directory = repository_root / arguments.output_directory / figure_subdirectory

        if figure_name == "entropy-by-geography":
            from national_figures.plot_entropy_by_geography import plot_entropy_by_geography

            config = load_configuration(
                arguments.config or repository_root / "code/configs/replication.yaml"
            )

            selection_folder = f"WB_{build_study_area_label(config)}"

            plot_entropy_by_geography(config, output_directory, data_directory / selection_folder)

        elif figure_name == "grid-vs-national-scores":
            from national_figures.plot_grid_vs_national_scores import plot_grid_vs_national_scores

            config = load_configuration(
                arguments.config or repository_root / "code/configs/replication.yaml"
            )

            selection_folder = build_study_area_label(config)

            plot_grid_vs_national_scores(
                config, output_directory, data_directory / selection_folder
            )

        elif figure_name == "population-composition":
            from national_figures.plot_population_composition import plot_population_composition

            config = load_configuration(
                arguments.config or repository_root / "code/configs/replication.yaml"
            )
            selection_folder = build_study_area_label(config)

            plot_population_composition(config, output_directory, data_directory / selection_folder)

        elif figure_name == "score-ranks":
            from national_figures.plot_score_ranks import plot_score_rank_comparisons

            config = load_configuration(
                arguments.config or repository_root / "code/configs/replication.yaml"
            )
            selection_folder = build_study_area_label(config)

            plot_score_rank_comparisons(config, output_directory, data_directory / selection_folder)

        elif figure_name == "grid-reference-scores":
            from experiments.grid_configurations.plot_grid_reference_scores import (
                plot_grid_reference_scores,
            )

            plot_grid_reference_scores(data_directory, output_directory)

        elif figure_name == "grid-pop-share-arrangements":
            from experiments.grid_configurations.plot_grid_pop_share_arrangements import (
                plot_grid_pop_share_arrangements,
            )

            plot_grid_pop_share_arrangements(data_directory, output_directory)

        elif figure_name == "grid-score-comparisons":
            from experiments.grid_configurations.plot_grid_score_comparisons import (
                plot_grid_score_comparisons,
            )

            plot_grid_score_comparisons(data_directory, output_directory)

        elif figure_name == "national":
            from national_figures.plot_national_results import plot_national_figures

            config = load_configuration(
                arguments.config or repository_root / "code/configs/replication.yaml"
            )

            selection_folder = build_study_area_label(config)

            plot_national_figures(config, output_directory, data_directory / selection_folder)

        elif figure_name == "grid-distributions":
            from experiments.grid_configurations.plot_grid_distributions import (
                plot_grid_distributions,
            )

            plot_grid_distributions(data_directory, output_directory)

        elif figure_name == "capy-weights":
            from national_figures.plot_capy_weights import plot_capy_weight_comparison

            config = load_configuration(
                arguments.config or repository_root / "code/configs/replication.yaml"
            )

            selection_folder = build_study_area_label(config)

            plot_capy_weight_comparison(config, output_directory, data_directory / selection_folder)

        elif figure_name == "triangular":
            from experiments.reardon_osullivan.plot_triangular_lattices import (
                plot_triangular_lattices,
            )

            plot_triangular_lattices(data_directory, output_directory)


if __name__ == "__main__":
    main()
