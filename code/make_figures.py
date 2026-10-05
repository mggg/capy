"""Draw separate PNG figures and legends from saved results, without running experiments."""

import argparse
from pathlib import Path

from national_pipeline.derived_file_paths import build_study_area_label
from national_pipeline.pipeline_config import PipelineConfig, load_configuration

FIGURE_DIRECTORIES = {
    "national": ("national/processed_data/history", "national"),
    "score-ranks": ("national/processed_data/score_ranks", "national"),
    "population-composition": ("national/processed_data/population_composition", "national"),
    "capy-weights": ("national/processed_data/capy_weights", "national"),
    "grid-distributions": (
        "experiments/grid_configurations/distributions",
        "grid_configurations/distributions",
    ),
    "iowa": ("experiments/iowa_configurations", "iowa_configurations"),
    "dispersion": ("experiments/neighborhood_change", "neighborhood_change"),
    "triangular": ("experiments/reardon_osullivan", "reardon_osullivan"),
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
    "expanding-support": (
        "experiments/synthetic_diffusion/expanding_support",
        "synthetic_diffusion/expanding_support",
    ),
    "stochastic": ("experiments/synthetic_diffusion/stochastic", "synthetic_diffusion/stochastic"),
}


def main() -> None:
    """Draw selected image sets in argument order; an input or rendering failure stops the run."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=(
            "Selections run in the supplied order and stop on the first failure. "
            "Prepare their inputs with code/run_experiment.py first. "
            "Example from the repository root: python code/make_figures.py national score-ranks"
        ),
    )
    parser.add_argument(
        "figures",
        nargs="+",
        choices=FIGURE_DIRECTORIES,
        metavar="FIGURE",
        help="One or more saved-result figure sets. Choices: " + ", ".join(FIGURE_DIRECTORIES),
    )
    parser.add_argument(
        "--config",
        type=Path,
        help=(
            "YAML study-area, year, and geography settings for national figures only; "
            "use the settings that prepared the results. Defaults to code/configs/replication.yaml "
            "in the repository. An explicit relative filename starts at the current directory."
        ),
    )
    parser.add_argument(
        "--data-directory",
        type=Path,
        default=Path("results"),
        help=(
            "Root containing saved results, not an individual workflow folder. Workflow and "
            "national study-area subfolders are added automatically. Relative to the repository "
            "unless absolute (default: %(default)s)."
        ),
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path("figures"),
        help=(
            "Root for PNG figures and legends; each workflow adds its own subfolders. "
            "Relative to the repository unless absolute (default: %(default)s)."
        ),
    )
    arguments = parser.parse_args()
    repository_root = Path(__file__).resolve().parent.parent

    national_config: PipelineConfig | None = None

    for figure_name in arguments.figures:
        result_subdirectory, figure_subdirectory = FIGURE_DIRECTORIES[figure_name]
        data_directory = repository_root / arguments.data_directory / result_subdirectory
        output_directory = repository_root / arguments.output_directory / figure_subdirectory

        if result_subdirectory.startswith("national/"):
            if national_config is None:
                national_config = load_configuration(
                    arguments.config or repository_root / "code/configs/replication.yaml"
                )
            make_national_figure(national_config, figure_name, data_directory, output_directory)

        else:
            make_experiment_figure(figure_name, data_directory, output_directory)


def make_national_figure(
    national_config: PipelineConfig, figure_name: str, data_directory: Path, output_directory: Path
) -> None:
    """Draw national figures and legends from saved results.

    Input-validation, file-access, and rendering errors from the selected plotting workflow
    propagate to the caller.

    Args:
        national_config (PipelineConfig): Study areas, Census years/levels, and upstream input
            folders.
        figure_name (str): A national selection from FIGURE_DIRECTORIES.
        data_directory (Path): Selected workflow's result directory before adding the study-area
            subfolder. Entropy uses the study-area label prefixed with WB_.
        output_directory (Path): Destination for PNG figures and legends.
    """

    selection_folder = build_study_area_label(national_config)
    if figure_name == "entropy-by-geography":
        selection_folder = f"WB_{selection_folder}"

    data_directory /= selection_folder

    match figure_name:
        case "entropy-by-geography":
            from national_figures.plot_entropy_by_geography import plot_entropy_by_geography

            plot_entropy_by_geography(national_config, output_directory, data_directory)

        case "grid-vs-national-scores":
            from national_figures.plot_grid_vs_national_scores import (
                plot_grid_vs_national_scores,
            )

            plot_grid_vs_national_scores(national_config, output_directory, data_directory)

        case "population-composition":
            from national_figures.plot_population_composition import (
                plot_population_composition,
            )

            plot_population_composition(national_config, output_directory, data_directory)

        case "score-ranks":
            from national_figures.plot_score_ranks import plot_score_rank_comparisons

            plot_score_rank_comparisons(national_config, output_directory, data_directory)

        case "national":
            from national_figures.plot_national_results import plot_national_figures

            plot_national_figures(national_config, output_directory, data_directory)

        case "capy-weights":
            from national_figures.plot_capy_weights import plot_capy_weight_comparison

            plot_capy_weight_comparison(national_config, output_directory, data_directory)


def make_experiment_figure(figure_name: str, data_directory: Path, output_directory: Path) -> None:
    """Draw figures and legends from saved experiment results.

    Input-validation, file-access, and rendering errors from the selected plotting workflow
    propagate to the caller.

    Args:
        figure_name (str): A non-national selection from FIGURE_DIRECTORIES.
        data_directory (Path): Location of saved results for the selected figure.
        output_directory (Path): Destination for PNG figures and legends.
    """

    match figure_name:
        case "grid-reference-scores":
            from experiments.grid_configurations.plot_grid_reference_scores import (
                plot_grid_reference_scores,
            )

            plot_grid_reference_scores(data_directory, output_directory)

        case "grid-pop-share-arrangements":
            from experiments.grid_configurations.plot_grid_pop_share_arrangements import (
                plot_grid_pop_share_arrangements,
            )

            plot_grid_pop_share_arrangements(data_directory, output_directory)

        case "grid-score-comparisons":
            from experiments.grid_configurations.plot_grid_score_comparisons import (
                plot_grid_score_comparisons,
            )

            plot_grid_score_comparisons(data_directory, output_directory)

        case "expanding-support":
            from experiments.synthetic_diffusion.plot_expanding_support import (
                plot_expanding_support,
            )

            plot_expanding_support(data_directory, output_directory)

        case "stochastic":
            from experiments.synthetic_diffusion.plot_stochastic_diffusion import (
                plot_stochastic_diffusion,
            )

            plot_stochastic_diffusion(data_directory, output_directory)

        case "dispersion":
            from experiments.neighborhood_change.plot_observed_dispersion import (
                plot_observed_dispersion,
            )

            plot_observed_dispersion(data_directory, output_directory)

        case "iowa":
            from experiments.iowa_configurations.plot_county_configurations import (
                plot_iowa_experiments,
            )

            plot_iowa_experiments(data_directory, output_directory)

        case "grid-distributions":
            from experiments.grid_configurations.plot_grid_distributions import (
                plot_grid_distributions,
            )

            plot_grid_distributions(data_directory, output_directory)

        case "triangular":
            from experiments.reardon_osullivan.plot_triangular_lattices import (
                plot_triangular_lattices,
            )

            plot_triangular_lattices(data_directory, output_directory)


if __name__ == "__main__":
    main()
