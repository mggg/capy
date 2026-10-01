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

        if figure_name == "population-composition":
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

        elif figure_name == "national":
            from national_figures.plot_national_results import plot_national_figures

            config = load_configuration(
                arguments.config or repository_root / "code/configs/replication.yaml"
            )

            selection_folder = build_study_area_label(config)

            plot_national_figures(config, output_directory, data_directory / selection_folder)

        elif figure_name == "capy-weights":
            from national_figures.plot_capy_weights import plot_capy_weight_comparison

            config = load_configuration(
                arguments.config or repository_root / "code/configs/replication.yaml"
            )

            selection_folder = build_study_area_label(config)

            plot_capy_weight_comparison(config, output_directory, data_directory / selection_folder)


if __name__ == "__main__":
    main()
