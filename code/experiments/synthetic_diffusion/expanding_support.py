"""Nine continuous-population diffusion experiments on a 20×20 rook grid."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.ndimage import distance_transform_cdt

from experiments.experiment_scores import ExperimentScores, calculate_experiment_scores
from experiments.grid_adjacency import build_grid_adjacency


class SupportShape(StrEnum):
    """Initial support and its expansion rule on the grid."""

    CENTERED_RECTANGLE = "centered_rectangle"
    ROOK_EXPANDING_CORE = "rook_expanding_core"
    THICK_CROSS = "thick_cross"


class Demography(StrEnum):
    """Change in total first-group mass as its support expands."""

    CONSTANT = "constant"
    GROWTH = "growth"
    DECLINE = "decline"


@dataclass(frozen=True)
class ExpandingSupportTrajectory:
    """One shape and demography's first-group shares, indexed by step, row, and column.

    Each cell has total mass one; second-group shares are the complement of these shares.
    """

    shape: SupportShape
    demography: Demography
    shares: np.ndarray


@dataclass(frozen=True)
class ExpandingSupportResult:
    """Scores and occupied area for one step of a demographic trajectory.

    Support fraction is the fraction of grid cells with positive first-group population. Expansion
    progress runs from zero at the initial support to one at the final grid.
    """

    shape: SupportShape
    demography: Demography
    step: int
    support_fraction: float
    expansion_progress: float
    scores: ExperimentScores

    def to_record(self) -> dict[str, float | str | None]:
        """Flatten the step description and scores into one table row."""
        return {
            "shape": self.shape,
            "demography": self.demography,
            "step": self.step,
            "support_fraction": self.support_fraction,
            "expansion_progress": self.expansion_progress,
            **self.scores.to_record(),
        }


def build_expanding_support_masks() -> dict[SupportShape, np.ndarray]:
    """Build nested population-support masks on a 20×20 grid.

    True marks cells where the first group can be present; masks do not assign population counts
    or shares. Each mask contains the previous one, and each family fills the grid. The centered
    rectangle starts at 10×10, then adds a column on each side and a row above and below in
    alternation: 10×10, 10×12, 12×12, ..., 20×20. The rook core starts as a 5×5 square at
    zero-based rows and columns 8–12. Each step adds cells one more horizontal or vertical grid
    edge from that initial square. The cross initially spans rows and columns 1–18 with arms three
    cells wide, at indices 8–10. It expands by the same horizontal-or-vertical distance rule as
    the core.

    Returns:
        dict[SupportShape, np.ndarray]: Shapes mapped to Boolean arrays indexed by step, row, and
            column, with 20×20 cells per mask (11 rectangle, 17 core, 11 cross steps).
    """
    rectangles = []

    for step in range(11):
        height, width = 10 + 2 * (step // 2), 10 + 2 * ((step + 1) // 2)
        mask = np.zeros((20, 20), dtype=bool)
        row, column = (20 - height) // 2, (20 - width) // 2
        mask[row : row + height, column : column + width] = True
        rectangles.append(mask)

    core = np.zeros((20, 20), dtype=bool)
    core[8:13, 8:13] = True

    cross = np.zeros_like(core)
    cross[1:19, 8:11] = True
    cross[8:11, 1:19] = True

    masks_by_shape = {SupportShape.CENTERED_RECTANGLE: np.array(rectangles)}

    for shape, initial_mask in (
        (SupportShape.ROOK_EXPANDING_CORE, core),
        (SupportShape.THICK_CROSS, cross),
    ):
        distances = np.asarray(distance_transform_cdt(~initial_mask, metric="taxicab"))
        masks_by_shape[shape] = np.array(
            [distances <= step for step in range(int(distances.max()) + 1)]
        )

    return masks_by_shape


def build_expanding_support_trajectories(
    shape: SupportShape, masks: np.ndarray
) -> list[ExpandingSupportTrajectory]:
    """Build constant, growing, and declining first-group populations for one support shape.

    Each cell has total mass one. The first group is uniform inside its support and absent
    outside it. Constant variants preserve its total mass. Overall grid shares finish at 0.4/0.1
    under growth/decline for rectangle and cross, or 0.1/0.025 for the core. Overall shares vary
    linearly with step for rectangle/core and with occupied area for cross. Shares inside the
    occupied cells are the overall shares divided by the support fractions.

    Args:
        shape (SupportShape): Shape whose demographic schedule to use.
        masks (np.ndarray): Its nested Boolean support masks in step, row, column order,
            beginning with nonempty support and ending with the full grid.

    Returns:
        list[ExpandingSupportTrajectory]: Constant, growth, and decline trajectories in that order.
    """
    support_fractions = masks.mean(axis=(1, 2))
    initial_group_share = support_fractions[0]
    demographic_progress = np.linspace(0, 1, len(masks))

    if shape == SupportShape.THICK_CROSS:
        demographic_progress = (support_fractions - initial_group_share) / (1 - initial_group_share)

    final_group_shares = {
        Demography.CONSTANT: initial_group_share,
        Demography.GROWTH: 0.4,
        Demography.DECLINE: 0.1,
    }

    if shape == SupportShape.ROOK_EXPANDING_CORE:
        final_group_shares[Demography.GROWTH] = 0.1
        final_group_shares[Demography.DECLINE] = 0.025

    trajectories = []

    for demography, final_group_share in final_group_shares.items():
        overall_group_shares = initial_group_share + demographic_progress * (
            final_group_share - initial_group_share
        )
        occupied_cell_shares = overall_group_shares / support_fractions
        trajectories.append(
            ExpandingSupportTrajectory(
                shape=shape,
                demography=demography,
                shares=masks * occupied_cell_shares[:, None, None],
            )
        )

    return trajectories


def run_expanding_support(data_directory: Path) -> None:
    """Compute the trajectories and save scores and arrays for independent plotting.

    Args:
        data_directory (Path): Result root. Each shape subfolder receives
            expanding_support_scores.parquet and states.npz.

    Raises:
        OSError: A result cannot be written.
    """
    adjacency = build_grid_adjacency(20)

    for shape, masks in build_expanding_support_masks().items():
        trajectories = build_expanding_support_trajectories(shape, masks)
        results: list[ExpandingSupportResult] = []

        for trajectory in trajectories:
            for step, grid in enumerate(trajectory.shares):
                results.append(
                    ExpandingSupportResult(
                        shape=trajectory.shape,
                        demography=trajectory.demography,
                        step=step,
                        support_fraction=float((grid > 0).mean()),
                        expansion_progress=step / (len(trajectory.shares) - 1),
                        scores=calculate_experiment_scores(
                            adjacency, grid.ravel(), 1 - grid.ravel()
                        ),
                    )
                )

        scores_df = pd.DataFrame([result.to_record() for result in results])
        shape_states = {
            f"{trajectory.shape}_{trajectory.demography}": trajectory.shares
            for trajectory in trajectories
        }
        shape_directory = data_directory / shape
        shape_directory.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(shape_directory / "states.npz", allow_pickle=False, **shape_states)
        scores_df.to_parquet(shape_directory / "expanding_support_scores.parquet", index=False)
