"""Compare quadratic Capy under zero, unit, and limiting neighbor weights."""

from pathlib import Path

import numpy as np
import pandas as pd
from capy_metrics import (
    aspatial_capy,
    build_csr_adjacency_matrix,
    capy,
    node_attribute_to_numpy_arr,
)
from capy_metrics.errors import UndefinedMetricError, UndefinedMetricReason
from capy_metrics.inputs import prepare_population_vectors, prepare_weight_matrix
from national_pipeline.assign_study_areas.study_area_columns import (
    MembershipColumn,
    StudyAreaColumn,
)
from national_pipeline.build_graphs.archive_inventory import read_graph_selection_summary
from national_pipeline.build_graphs.build_area_graph import GraphStatus
from national_pipeline.build_graphs.graph_archives import read_graph_from_archive
from national_pipeline.compute_metrics.metric_types import MetricColumn, PopulationComparison
from national_pipeline.geography_types import GeographyLevel, StudyAreaType
from national_pipeline.pipeline_config import PipelineConfig
from national_pipeline.population_table_columns import PopulationColumn
from scipy import sparse


def limiting_quadratic_capy(
    adjacency: sparse.csr_array,
    first: np.ndarray,
    second: np.ndarray,
) -> float:
    r"""Compute the limit as neighbor weight grows in $W=I+\lambda A$.

    Each group's fraction uses its adjacency inner products when their denominator is positive. If
    a group has no neighbor interactions, its within-unit fraction persists in the limit.

    Args:
        adjacency (sparse.csr_array): Symmetric nonnegative adjacency with zero diagonal.
        first (np.ndarray): Nonnegative first-group populations in matrix order.
        second (np.ndarray): Nonnegative second-group populations in matrix order.

    Returns:
        float: Quadratic limiting Capy, retaining within-unit fallback for isolated populations.

    Raises:
        ValueError: Matrix or population inputs are invalid.
        UndefinedMetricError: A group is absent, so its fraction is undefined.
    """
    first, second = prepare_population_vectors(first, second)
    adjacency = prepare_weight_matrix(adjacency, len(first))

    if (
        np.any(adjacency.data < 0)
        or np.any(adjacency.diagonal() != 0)
        or (adjacency != adjacency.T).nnz
    ):
        raise ValueError("Capy adjacency must be symmetric, nonnegative, and zero-diagonal")

    fractions = []

    for group, complement in ((first, second), (second, first)):
        within = float(group @ (adjacency @ group))
        between = float(group @ (adjacency @ complement))

        if within + between == 0:
            within = float(group @ group)
            between = float(group @ complement)

        if within + between == 0:
            raise UndefinedMetricError(UndefinedMetricReason.NO_PAIR_INTERACTIONS)

        fractions.append(within / (within + between))

    return sum(fractions) / 2


def run_capy_weight_comparison(
    config: PipelineConfig, repository_root: Path, data_directory: Path
) -> None:
    """Save Capy neighbor-weight comparisons for CBSA tracts in the configured years.

    Within each year, the 100 largest retained populations with ready CBSA tract graphs are
    selected before scoring. Population ties are broken by area ID. Each configured population
    comparison uses those same graph nodes. Missing graphs or undefined scores stop the
    calculation rather than removing an area from the ranking.

    Args:
        config (PipelineConfig): Must select CBSAs and include tracts. Other geography levels are
            ignored; configured years, vintage, and population comparisons are retained. Metric
            selection does not alter this experiment's zero, unit, and limiting weights.
        repository_root (Path): Base for relative configured input directories.
        data_directory (Path): Destination for capy_weights.parquet, including selection
            identities.

    Raises:
        OSError: A source table/archive cannot be read or the output cannot be written.
        ValueError: The configuration does not select CBSA tracts, or a selection lacks graph
            accounting, definitions, or valid metric inputs.
        KeyError: A selected graph member or required attribute is missing.
        UndefinedMetricError: A comparison has no eligible interactions for a group.
    """
    if (
        config.study_area_type != StudyAreaType.CBSA
        or GeographyLevel.TRACT not in config.census_geography_levels
    ):
        raise ValueError("Capy-weight comparisons require CBSAs with tracts selected")

    area_folder = Path(config.study_area_type) / str(config.study_area_vintage)
    definitions_df = pd.read_parquet(
        repository_root / config.study_area_directory / area_folder / "definitions.parquet",
        columns=[StudyAreaColumn.STUDY_AREA_ID, StudyAreaColumn.NAME],
    )
    graph_directory = repository_root / config.graph_archive_directory
    score_tables = []

    for year in sorted(set(config.census_geography_years)):
        archive_path = (
            graph_directory
            / f"{config.study_area_type}_{config.study_area_vintage}_{year}_{GeographyLevel.TRACT}.zip"
        )

        summary_df = read_graph_selection_summary(archive_path, year, GeographyLevel.TRACT)

        if summary_df.empty:
            raise ValueError(f"No graph accounting for {year} tracts")

        ready_graphs_df = summary_df.loc[summary_df[MembershipColumn.STATUS].eq(GraphStatus.READY)]

        if ready_graphs_df.empty:
            raise ValueError(f"No ready graphs for {year} tracts")

        largest_areas_df = ready_graphs_df.sort_values(
            ["retained_TOTPOP", StudyAreaColumn.STUDY_AREA_ID], ascending=[False, True]
        ).head(100)

        largest_areas_df = largest_areas_df.merge(
            definitions_df, on=StudyAreaColumn.STUDY_AREA_ID, how="left", validate="one_to_one"
        )

        if largest_areas_df[StudyAreaColumn.NAME].isna().any():
            raise ValueError("Population-ranked areas lack study-area definitions")

        scores_df = compute_capy_weight_scores_from_archives(
            largest_areas_df, config.population_comparisons, graph_directory
        )
        scores_df[MembershipColumn.CENSUS_YEAR] = year
        scores_df[MembershipColumn.GEOGRAPHY_LEVEL] = GeographyLevel.TRACT
        score_tables.append(scores_df)

    scores_df = pd.concat(score_tables, ignore_index=True)
    data_directory.mkdir(parents=True, exist_ok=True)
    scores_df.to_parquet(data_directory / "capy_weights.parquet", index=False)


def compute_capy_weight_scores_from_archives(
    selected_graphs_df: pd.DataFrame,
    comparisons: tuple[PopulationComparison, ...],
    graph_directory: Path,
) -> pd.DataFrame:
    """Read a population-selected graph sample and compute three Capy weights and ranks.

    Args:
        selected_graphs_df (pd.DataFrame): One year/level's graph archive members, area IDs, and
            names.
        comparisons (tuple[PopulationComparison, ...]): Population pairs to score for every graph.
        graph_directory (Path): Directory containing the referenced graph archives.

    Returns:
        pd.DataFrame: Zero, unit, and limiting-weight scores with ascending average-tie ranks
            within each population comparison.

    Raises:
        OSError: An archive cannot be read.
        KeyError: A graph member or required attribute is missing.
        ValueError: Graph metric inputs are invalid.
        UndefinedMetricError: A score has no eligible group interactions.
    """
    rows = []

    for _, graph_summary in selected_graphs_df.iterrows():
        graph = read_graph_from_archive(
            graph_directory / graph_summary["archive"], str(graph_summary["graph_member"])
        )
        adjacency = build_csr_adjacency_matrix(graph)
        white_population = node_attribute_to_numpy_arr(graph, PopulationColumn.NON_HISPANIC_WHITE)

        for comparison in comparisons:
            second_population = node_attribute_to_numpy_arr(
                graph, comparison.second_population_column
            )
            rows.append(
                {
                    StudyAreaColumn.STUDY_AREA_ID: graph_summary[StudyAreaColumn.STUDY_AREA_ID],
                    "name": graph_summary[StudyAreaColumn.NAME],
                    MetricColumn.COMPARISON: comparison.value,
                    "zero": aspatial_capy(white_population, second_population),
                    "unit": capy(adjacency, white_population, second_population),
                    "limit": limiting_quadratic_capy(
                        adjacency, white_population, second_population
                    ),
                }
            )

    scores_df = pd.DataFrame(rows)
    ranks_df = (
        scores_df.groupby(MetricColumn.COMPARISON)[["zero", "unit", "limit"]]
        .rank(ascending=True, method="average")
        .add_suffix("_rank")
    )
    return scores_df.join(ranks_df)
