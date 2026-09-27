"""Individual segregation metrics from numerical inputs or NetworkX graph attributes.

Functions ending in _from_graph read named node attributes. Their numerical counterparts accept
aligned arrays and matrices, so callers can reuse prepared inputs. Every score function returns a
float or raises UndefinedMetricError for a mathematical limitation. No function reads files,
modifies its inputs, or depends on pipeline configuration or study-specific population names.
"""

from .assortativity import (
    edge_assortativity,
    edge_assortativity_from_graph,
    half_edge_assortativity,
    half_edge_assortativity_from_graph,
)
from .capy import (
    aspatial_capy,
    aspatial_capy_from_graph,
    capy,
    capy_exact,
    capy_exact_from_graph,
    capy_from_graph,
)
from .errors import UndefinedMetricError, UndefinedMetricReason
from .evenness import (
    dissimilarity,
    dissimilarity_from_graph,
    relative_diversity,
    relative_diversity_from_graph,
    theil_information,
    theil_information_from_graph,
)
from .inputs import build_csr_adjacency_matrix
from .moran import (
    MoranWeightType,
    build_moran_weights,
    distance_morans_I,
    morans_I,
    morans_I_from_graph,
)

__all__ = [
    "MoranWeightType",
    "UndefinedMetricError",
    "UndefinedMetricReason",
    "aspatial_capy",
    "aspatial_capy_from_graph",
    "build_csr_adjacency_matrix",
    "build_moran_weights",
    "capy",
    "capy_exact",
    "capy_exact_from_graph",
    "capy_from_graph",
    "dissimilarity",
    "dissimilarity_from_graph",
    "distance_morans_I",
    "edge_assortativity",
    "edge_assortativity_from_graph",
    "half_edge_assortativity",
    "half_edge_assortativity_from_graph",
    "morans_I",
    "morans_I_from_graph",
    "relative_diversity",
    "relative_diversity_from_graph",
    "theil_information",
    "theil_information_from_graph",
]
