"""Analytic score curves for equal-mass populations on a four-neighbor square lattice."""

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import entr


def build_grid_reference_scores(group_shares: np.ndarray | None = None) -> pd.DataFrame:
    r"""Evaluate ten score conventions on idealized four-regular square-lattice arrangements.

    Every cell has combined mass one and the first group's mean share is $\rho$. Checkerboard
    cells alternate shares $2\rho$ and zero, giving local shares $2\rho/5$ and $8\rho/5$ under
    $W=I+A$. Constant cells all have share $\rho$. An isolated arrangement assigns pure first-
    group cells to an independent set of density $\rho$. Cluster curves are limits of large pure
    regions whose boundary-to-area ratio tends to zero; they are not finite-grid scores.

    All reference curves use `capy`, treating populations as continuous masses and retaining
    self-pair terms. Moran uses either $I+A$ or row-standardized $A/4$. Constant Moran is
    undefined and omitted. Isolated spatial evenness curves are also omitted: density alone does
    not determine the distribution of first-group neighbors at second-group cells. These curves
    describe the specified arrangements, not universal attainable bounds.

    Args:
        group_shares (np.ndarray | None): One-dimensional finite shares in (0, 0.5]. Defaults
            to 500 evenly spaced values from 0.005 to 0.5.

    Returns:
        pd.DataFrame: Long-form arrangement, metric, group_share, and value columns.

    Raises:
        ValueError: Shares are empty, nonfinite, nonscalar-per-row, or outside (0, 0.5].
    """
    rho = np.linspace(0.005, 0.5, 500) if group_shares is None else np.asarray(group_shares, float)

    if rho.ndim != 1 or not rho.size or not np.isfinite(rho).all():
        raise ValueError("Use a nonempty one-dimensional array of finite group shares")
    if np.any((rho <= 0) | (rho > 0.5)):
        raise ValueError("The idealized arrangements require shares in (0, 0.5]")

    entropy = entr(rho) + entr(1 - rho)
    checker_entropy = entr(2 * rho) + entr(1 - 2 * rho)
    low_local_share, high_local_share = 2 * rho / 5, 8 * rho / 5
    local_entropy = (
        entr(low_local_share)
        + entr(1 - low_local_share)
        + entr(high_local_share)
        + entr(1 - high_local_share)
    ) / 2
    ones, zeros = np.ones_like(rho), np.zeros_like(rho)
    curves = {
        "dissimilarity": {
            "cluster": ones,
            "constant": zeros,
            "isolated": ones,
            "checkerboard": 1 / (2 * (1 - rho)),
        },
        "entropy_index": {
            "cluster": ones,
            "constant": zeros,
            "isolated": ones,
            "checkerboard": 1 - checker_entropy / (2 * entropy),
        },
        "relative_diversity": {
            "cluster": ones,
            "constant": zeros,
            "isolated": ones,
            "checkerboard": rho / (1 - rho),
        },
        "aspatial_capy": {
            "cluster": ones,
            "constant": ones / 2,
            "isolated": ones,
            "checkerboard": 1 / (2 * (1 - rho)),
        },
        "spatial_dissimilarity": {
            "cluster": ones,
            "constant": zeros,
            "checkerboard": 3 / (10 * (1 - rho)),
        },
        "spatial_entropy_index": {
            "cluster": ones,
            "constant": zeros,
            "checkerboard": 1 - local_entropy / entropy,
        },
        "spatial_relative_diversity": {
            "cluster": ones,
            "constant": zeros,
            "checkerboard": 9 * rho / (25 * (1 - rho)),
        },
        "capy": {
            "cluster": ones,
            "constant": ones / 2,
            "isolated": (3 - 5 * rho) / (5 * (1 - rho)),
            "checkerboard": (5 - 8 * rho) / (10 * (1 - rho)),
        },
        "moran_with_self": {
            "cluster": ones,
            "isolated": (1 - 5 * rho) / (5 * (1 - rho)),
            "checkerboard": -0.6 * ones,
        },
        "moran_row_standardized": {
            "cluster": ones,
            "isolated": -rho / (1 - rho),
            "checkerboard": -ones,
        },
    }
    score_tables = [
        pd.DataFrame(
            {"arrangement": arrangement, "metric": metric, "group_share": rho, "value": values}
        )
        for metric, arrangements in curves.items()
        for arrangement, values in arrangements.items()
    ]

    return pd.concat(score_tables, ignore_index=True)


def save_grid_reference_scores(data_directory: Path) -> None:
    """Save the default analytic arrangement curves for ten score conventions.

    Args:
        data_directory (Path): Destination for theoretical_scores.parquet.

    Raises:
        OSError: The destination cannot be created or the score table cannot be written.
    """
    scores_df = build_grid_reference_scores()
    data_directory.mkdir(parents=True, exist_ok=True)
    scores_df.to_parquet(data_directory / "theoretical_scores.parquet", index=False)
