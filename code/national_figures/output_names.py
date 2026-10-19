"""Compact selection labels for national figures and their prepared results."""

from national_pipeline.compute_metrics.metric_types import PopulationComparison

POPULATION_COMPARISON_LABELS = {
    PopulationComparison.WHITE_BLACK: "WB",
    PopulationComparison.WHITE_POC: "WPOC",
}
