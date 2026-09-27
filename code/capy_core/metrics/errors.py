"""Name unavailable-score outcomes and distinguish undefined formulas from malformed inputs."""

from enum import StrEnum


class UndefinedMetricReason(StrEnum):
    """Reasons a requested score has no numeric value."""

    NO_GRAPH = "no_graph"  # Callers can record an absent graph without invoking a metric.
    ABSENT_POPULATION_GROUP = "absent_population_group"
    NO_PAIR_INTERACTIONS = "no_pair_interactions"
    ZERO_SHARE_VARIANCE = "zero_share_variance"
    NO_NEIGHBORS = "no_neighbors"
    ABSENT_MAJORITY_CLASS = "absent_majority_class"
    COINCIDENT_CENTROIDS = "coincident_centroids"


class UndefinedMetricError(ValueError):
    """A valid input has no defined score; reason identifies the mathematical limitation.

    Args:
        reason (UndefinedMetricReason): Stable reason that a caller can report or handle.
    """

    def __init__(self, reason: UndefinedMetricReason) -> None:
        """Retain the reason and use its value as the exception message."""
        self.reason = reason
        super().__init__(reason.value)
