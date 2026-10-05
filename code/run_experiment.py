"""Prepare numerical experiment results and national figure data without drawing images."""

import argparse
from pathlib import Path

from national_pipeline.derived_file_paths import build_study_area_label
from national_pipeline.pipeline_config import PipelineConfig, load_configuration

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
    "expanding-support": "experiments/synthetic_diffusion/expanding_support",
    "stochastic": "experiments/synthetic_diffusion/stochastic",
    "dispersion": "experiments/neighborhood_change",
    "iowa": "experiments/iowa_configurations",
    "grid-distributions": "experiments/grid_configurations/distributions",
    "capy-weights": "national/processed_data/capy_weights",
    "triangular": "experiments/reardon_osullivan",
}


def main() -> None:
    """Run selected experiments in argument order, stopping if any experiment fails."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=(
            "Experiments run in the supplied order and stop on the first failure. "
            "Options affect only the selected workflows that use them. "
            "Draw saved results afterward with code/make_figures.py. "
            "Example from the repository root: python code/run_experiment.py national score-ranks"
        ),
    )
    parser.add_argument(
        "experiments",
        nargs="+",
        choices=EXPERIMENT_DIRECTORIES,
        metavar="EXPERIMENT",
        help="One or more workflows to compute. Choices: " + ", ".join(EXPERIMENT_DIRECTORIES),
    )
    parser.add_argument(
        "--config",
        type=Path,
        help=(
            "YAML settings for national workflows, dispersion, and iowa; ignored by other "
            "experiments. Defaults to code/configs/max_city.yaml for dispersion and "
            "code/configs/replication.yaml otherwise, both in the repository. "
            "An explicit relative filename starts at the current directory."
        ),
    )
    parser.add_argument(
        "--data-directory",
        type=Path,
        default=Path("results"),
        help=(
            "Root for computed results and tables, not an individual workflow folder. Workflow "
            "and national study-area subfolders are added automatically. Relative to the "
            "repository unless absolute (default: %(default)s)."
        ),
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=10000,
        help=(
            "grid-distributions: independent binary grids per clustering class; "
            "must be positive (default: %(default)s)."
        ),
    )
    parser.add_argument(
        "--samples-per-share",
        type=int,
        default=500,
        help=(
            "iowa: sampling attempts per target population share and arrangement family; "
            "must be positive (default: %(default)s)."
        ),
    )
    parser.add_argument(
        "--share-count",
        type=int,
        default=100,
        help=(
            "iowa: evenly spaced target population shares per arrangement family; "
            "must be at least 2 (default: %(default)s)."
        ),
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=20260918,
        help=(
            "Base random seed for grid-pop-share-arrangements, grid-score-comparisons, "
            "grid-distributions, and iowa (default: %(default)s)."
        ),
    )
    parser.add_argument(
        "--buffer-steps",
        type=int,
        default=3,
        help=(
            "dispersion: neighborhood buffer retained for maps, from 0 to 10 graph steps. "
            "Scores and memberships include all buffers (default: %(default)s)."
        ),
    )
    parser.add_argument(
        "--moon-source-directory",
        type=Path,
        help=(
            "stochastic: required source root containing scripts/synthetic/stochastic_data. "
            "Relative to the repository unless absolute; ignored by other experiments."
        ),
    )
    arguments = parser.parse_args()

    if "stochastic" in arguments.experiments and arguments.moon_source_directory is None:
        parser.error("stochastic requires --moon-source-directory")

    repository_root = Path(__file__).resolve().parent.parent
    results_directory = repository_root / arguments.data_directory

    national_config: PipelineConfig | None = None

    for experiment_name in arguments.experiments:
        result_subdirectory = EXPERIMENT_DIRECTORIES[experiment_name]
        data_directory = results_directory / result_subdirectory

        if result_subdirectory.startswith("national/"):
            if national_config is None:
                national_config = load_configuration(
                    arguments.config or repository_root / "code/configs/replication.yaml"
                )

            run_national_experiment(
                national_config, experiment_name, repository_root, results_directory, data_directory
            )

        else:
            run_experiment(
                experiment_name,
                repository_root,
                data_directory,
                config_path=arguments.config,
                samples=arguments.samples,
                samples_per_share=arguments.samples_per_share,
                share_count=arguments.share_count,
                seed=arguments.seed,
                buffer_steps=arguments.buffer_steps,
                moon_source_directory=arguments.moon_source_directory,
            )


def run_national_experiment(
    national_config: PipelineConfig,
    experiment_name: str,
    repository_root: Path,
    results_directory: Path,
    data_directory: Path,
) -> None:
    """Prepare national results in a study-area subfolder.

    Input validation and file-access errors from the selected workflow propagate to the caller.

    Args:
        national_config (PipelineConfig): Study areas, Census years/levels, and input folders.
        experiment_name (str): A national workflow from EXPERIMENT_DIRECTORIES.
        repository_root (Path): Base for configured relative input paths.
        results_directory (Path): Result root, also used for the separate score-rank tables.
        data_directory (Path): Workflow destination before adding the study-area subfolder.
    """

    selection_folder = build_study_area_label(national_config)
    if experiment_name == "entropy-by-geography":
        selection_folder = f"WB_{selection_folder}"

    data_directory /= selection_folder

    match experiment_name:
        case "national":
            from national_figures.prepare_national_results import prepare_national_figure_data

            prepare_national_figure_data(national_config, repository_root, data_directory)

        case "entropy-by-geography":
            from national_figures.prepare_entropy_by_geography import prepare_entropy_data

            prepare_entropy_data(national_config, repository_root, data_directory)

        case "grid-vs-national-scores":
            from national_figures.prepare_grid_vs_national_scores import (
                prepare_grid_vs_national_scores,
            )

            prepare_grid_vs_national_scores(national_config, repository_root, data_directory)

        case "population-composition":
            from national_figures.prepare_population_composition import (
                prepare_population_composition_data,
            )

            prepare_population_composition_data(national_config, repository_root, data_directory)

        case "score-ranks":
            from national_figures.prepare_score_ranks import prepare_score_rank_data

            table_directory = results_directory / "national/tables/score_ranks"

            prepare_score_rank_data(
                national_config,
                repository_root,
                data_directory,
                table_directory / selection_folder,
            )

        case "ranked-population-table":
            from national_figures.prepare_ranked_table import prepare_ranked_population_table

            prepare_ranked_population_table(national_config, repository_root, data_directory)

        case "capy-weights":
            from national_figures.compare_capy_weights import run_capy_weight_comparison

            run_capy_weight_comparison(national_config, repository_root, data_directory)


def run_experiment(
    experiment_name: str,
    repository_root: Path,
    data_directory: Path,
    *,
    config_path: Path | None,
    samples: int,
    samples_per_share: int,
    share_count: int,
    seed: int,
    buffer_steps: int,
    moon_source_directory: Path | None,
) -> None:
    """Run a grid, diffusion, neighborhood, or Iowa experiment and save its results.

    Only the options used by the selected experiment affect its execution. Configuration,
    input validation, and file-access errors from the selected workflow propagate to the caller.

    Args:
        experiment_name (str): A non-national workflow from EXPERIMENT_DIRECTORIES.
        repository_root (Path): Base for relative input paths and default configuration files.
        data_directory (Path): Destination for the selected experiment's results.
        config_path (Path | None): YAML configuration for dispersion or Iowa; None selects
            max_city.yaml for dispersion and replication.yaml for Iowa.
        samples (int): Binary grids per class for grid distributions.
        samples_per_share (int): Iowa samples per target population share.
        share_count (int): Number of Iowa target population shares.
        seed (int): Random seed for grid arrangements, comparisons, distributions, and Iowa.
        buffer_steps (int): Neighborhood buffer for observed dispersion.
        moon_source_directory (Path | None): Stochastic source root, relative to the repository
            unless absolute. Required only for stochastic diffusion.

    Raises:
        ValueError: Stochastic diffusion was selected without a source directory.
    """

    match experiment_name:
        case "grid-reference-scores":
            from experiments.grid_configurations.grid_reference_scores import (
                save_grid_reference_scores,
            )

            save_grid_reference_scores(data_directory)

        case "grid-pop-share-arrangements":
            from experiments.grid_configurations.grid_pop_share_arrangements import (
                run_grid_pop_share_arrangements,
            )

            run_grid_pop_share_arrangements(data_directory, seed)

        case "grid-score-comparisons":
            from experiments.grid_configurations.grid_score_comparisons import (
                run_grid_score_comparisons,
            )

            run_grid_score_comparisons(data_directory, seed)

        case "expanding-support":
            from experiments.synthetic_diffusion.expanding_support import run_expanding_support

            run_expanding_support(data_directory)

        case "stochastic":
            from experiments.synthetic_diffusion.stochastic_diffusion import (
                run_stochastic_diffusion,
            )

            if moon_source_directory is None:
                raise ValueError("stochastic requires a source directory")

            run_stochastic_diffusion(data_directory, repository_root / moon_source_directory)

        case "dispersion":
            from experiments.neighborhood_change.observed_dispersion import run_observed_dispersion

            config = load_configuration(
                config_path or repository_root / "code/configs/max_city.yaml"
            )

            run_observed_dispersion(config, repository_root, data_directory, buffer_steps)

        case "iowa":
            from experiments.iowa_configurations.county_configurations import run_iowa_experiments

            config = load_configuration(
                config_path or repository_root / "code/configs/replication.yaml"
            )

            run_iowa_experiments(
                config,
                repository_root,
                data_directory,
                samples_per_share,
                share_count,
                seed,
            )

        case "grid-distributions":
            from experiments.grid_configurations.grid_distributions import run_grid_distributions

            run_grid_distributions(data_directory, samples, seed)

        case "triangular":
            from experiments.reardon_osullivan.triangular_lattices import run_triangular_lattices

            run_triangular_lattices(data_directory)


if __name__ == "__main__":
    main()
