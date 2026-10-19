"""Names for population comparisons, reported scores, and missing or undefined results."""

from enum import StrEnum

from capy_metrics import UndefinedMetricReason

from national_pipeline.population_table_columns import PopulationColumn


class PopulationComparison(StrEnum):
    """Two-group populations evaluated on the shared White–Black-filtered graph."""

    WHITE_BLACK = "white_black"
    WHITE_POC = "white_poc"

    @property
    def second_population_column(self) -> PopulationColumn:
        """Return the group compared with non-Hispanic White residents."""
        if self == PopulationComparison.WHITE_BLACK:
            return PopulationColumn.NON_HISPANIC_BLACK

        return PopulationColumn.POC


class MetricName(StrEnum):
    """Supported scores; each name identifies a formula rather than a plotting label."""

    DISSIMILARITY = "dissimilarity"
    ENTROPY_INDEX = "entropy_index"
    RELATIVE_DIVERSITY = "relative_diversity"
    ASPATIAL_CAPY = "aspatial_capy"
    SPATIAL_DISSIMILARITY = "spatial_dissimilarity"
    SPATIAL_ENTROPY_INDEX = "spatial_entropy_index"
    SPATIAL_RELATIVE_DIVERSITY = "spatial_relative_diversity"
    CAPY = "capy"
    CAPY_EXACT = "capy_exact"
    MORAN_ADJACENCY = "moran_adjacency"
    MORAN_NEGATIVE_LAPLACIAN = "moran_negative_laplacian"
    MORAN_METROPOLIS = "moran_metropolis"
    MORAN_WITH_SELF = "moran_with_self"
    MORAN_ROW_STANDARDIZED = "moran_row_standardized"
    MORAN_INVERSE_DISTANCE = "moran_inverse_distance"
    MORAN_INVERSE_SQUARED_DISTANCE = "moran_inverse_squared_distance"
    EDGE_ASSORTATIVITY = "edge_assortativity"
    HALF_EDGE_ASSORTATIVITY = "half_edge_assortativity"


class MetricSkipReason(StrEnum):
    """Reasons the pipeline cannot run a metric, separate from undefined mathematics."""

    NO_GRAPH = "no_graph"


class MetricColumn(StrEnum):
    """Fields shared by per-area metric tables and their complete-history averages."""

    COMPARISON = "population_comparison"
    METRIC = "metric"
    VALUE = "value"
    UNDEFINED_REASON = "undefined_reason"
    GRAPH_STATUS = "graph_status"
    AVERAGE = "average_when_all_years_present"
    EXPECTED_YEARS = "expected_years"
    CONTRIBUTING_AREA_IDS = "contributing_area_ids"
    AREA_COUNT = "area_count"


# A result is either a finite number or an explanation, never a fabricated zero for missing data.
MetricValue = float | UndefinedMetricReason | MetricSkipReason
