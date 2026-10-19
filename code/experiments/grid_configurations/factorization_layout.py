"""Anneal paired population swaps while maintaining endpoint-weighted layout moments."""

from dataclasses import dataclass

import numpy as np

GRID_SIDE_LENGTH = 16
GRID_NODE_COUNT = GRID_SIDE_LENGTH**2


def swap_toward_target_layout(
    shares: np.ndarray,
    total_population: np.ndarray,
    target_layout: float,
    rng: np.random.Generator,
    steps: int = 6000,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Anneal paired population swaps toward an endpoint-weighted layout target.

    Temperature falls from 3e-3 toward 1e-7. Search stops when squared layout error is below 1e-4
    or proposals are exhausted. It may finish without reaching the target.

    Args:
        shares (np.ndarray): Validated length-256 shares in [0,1], in row-major grid order.
        total_population (np.ndarray): Aligned positive population masses. Inputs are copied.
        target_layout (float): Requested layout in [-0.6,1].
        rng (np.random.Generator): Generator advanced for proposals and acceptance decisions.
        steps (int): Maximum proposals, default 6,000. Zero returns the initial arrangement.

    Returns:
        tuple[np.ndarray, np.ndarray, float]: New shares, paired total populations, and incremental
            layout estimate. Swaps preserve the multiset of (share, population) pairs. The caller
            recomputes final scores before accepting a sample.
    """
    state = _LayoutSearchState(shares, total_population)
    error = (state.pair_totals.layout - target_layout) ** 2

    for step in range(steps):
        if error < 1e-4:
            break

        temperature = 3e-3 * (1e-7 / 3e-3) ** (step / steps)
        first, second = rng.integers(GRID_NODE_COUNT), rng.integers(GRID_NODE_COUNT)

        if first == second:
            continue

        proposed_totals = state.predict_swap_totals(first, second)
        proposed_error = (proposed_totals.layout - target_layout) ** 2

        if proposed_error > error and rng.random() >= np.exp(
            -(proposed_error - error) / temperature
        ):
            continue

        state.apply_swap(first, second, proposed_totals)
        error = proposed_error

    return (
        state.group_population / state.total_population,
        state.total_population,
        state.pair_totals.layout,
    )


@dataclass(frozen=True)
class _PairTotals:
    """Quadratic forms determining layout for W=I+A, x=group, t=total, and z=x²/t.

    group_pairs is xᵀWx; group_total_pairs is xᵀWt; population_pairs is tᵀWt;
    squared_share_pairs is zᵀWt. Dividing by population_pairs gives the moments of
    shares under endpoint weights t_i(Wt)_i.
    """

    group_pairs: float
    group_total_pairs: float
    population_pairs: float
    squared_share_pairs: float

    @property
    def layout(self) -> float:
        """Return normalized covariance, using zero when endpoint variance is negligible."""
        endpoint_share = self.group_total_pairs / self.population_pairs
        variance = self.squared_share_pairs / self.population_pairs - endpoint_share**2

        if variance <= 1e-15:
            return 0.0

        return (self.group_pairs / self.population_pairs - endpoint_share**2) / variance


class _LayoutSearchState:
    """Own populations, closed-neighbor sums, and their coupled quadratic forms during search.

    Initialization copies the caller's populations. Only apply_swap() changes this state; proposed
    totals are evaluated without modifying arrays. The search applies a proposal immediately or
    discards it, so a proposal never outlives the state on which it was calculated.
    """

    def __init__(self, shares: np.ndarray, total_population: np.ndarray) -> None:
        self.total_population = total_population.copy()
        self.group_population = shares * self.total_population
        self.squared_share_population = shares * self.group_population
        self.neighbors = _build_rook_neighbors()

        self.group_neighbor_sums = self._sum_closed_neighbors(self.group_population)
        self.total_neighbor_sums = self._sum_closed_neighbors(self.total_population)
        self.squared_share_neighbor_sums = self._sum_closed_neighbors(self.squared_share_population)
        self.pair_totals = _PairTotals(
            group_pairs=np.dot(self.group_population, self.group_neighbor_sums),
            group_total_pairs=np.dot(self.group_population, self.total_neighbor_sums),
            population_pairs=np.dot(self.total_population, self.total_neighbor_sums),
            squared_share_pairs=np.dot(self.squared_share_population, self.total_neighbor_sums),
        )

    def _sum_closed_neighbors(self, values: np.ndarray) -> np.ndarray:
        """Sum each unit and its rook neighbors in the fixed proposal-update order."""
        sums = values.copy()

        for node, neighbors in enumerate(self.neighbors):
            for neighbor in neighbors:
                sums[node] += values[neighbor]

        return sums

    def predict_swap_totals(self, first: int | np.integer, second: int | np.integer) -> _PairTotals:
        """Predict the four quadratic forms after swapping these two units' populations.

        A paired swap adds delta at the first unit and subtracts it at the second. Its quadratic
        correction is W_aa+W_bb-2W_ab: two self-weights minus two if the units are neighbors.
        Both populations and their existing neighborhood sums remain unchanged here.
        """
        quadratic_correction = 2.0 - (2.0 if second in self.neighbors[first] else 0.0)
        group_change = self.group_population[second] - self.group_population[first]
        total_change = self.total_population[second] - self.total_population[first]
        squared_share_change = (
            self.squared_share_population[second] - self.squared_share_population[first]
        )
        group_neighbor_difference = (
            self.group_neighbor_sums[first] - self.group_neighbor_sums[second]
        )
        total_neighbor_difference = (
            self.total_neighbor_sums[first] - self.total_neighbor_sums[second]
        )
        squared_share_neighbor_difference = (
            self.squared_share_neighbor_sums[first] - self.squared_share_neighbor_sums[second]
        )

        return _PairTotals(
            group_pairs=(
                self.pair_totals.group_pairs
                + 2 * group_change * group_neighbor_difference
                + group_change * group_change * quadratic_correction
            ),
            group_total_pairs=(
                self.pair_totals.group_total_pairs
                + group_change * total_neighbor_difference
                + total_change * group_neighbor_difference
                + group_change * total_change * quadratic_correction
            ),
            population_pairs=(
                self.pair_totals.population_pairs
                + 2 * total_change * total_neighbor_difference
                + total_change * total_change * quadratic_correction
            ),
            squared_share_pairs=(
                self.pair_totals.squared_share_pairs
                + squared_share_change * total_neighbor_difference
                + total_change * squared_share_neighbor_difference
                + squared_share_change * total_change * quadratic_correction
            ),
        )

    def apply_swap(
        self, first: int | np.integer, second: int | np.integer, proposed_totals: _PairTotals
    ) -> None:
        """Apply a proposal from the current state, keeping populations and cached sums aligned."""
        for population, neighbor_sums in (
            (self.group_population, self.group_neighbor_sums),
            (self.total_population, self.total_neighbor_sums),
            (self.squared_share_population, self.squared_share_neighbor_sums),
        ):
            change = population[second] - population[first]

            for node in (first, *self.neighbors[first]):
                neighbor_sums[node] += change

            for node in (second, *self.neighbors[second]):
                neighbor_sums[node] -= change

            population[first], population[second] = population[second], population[first]

        self.pair_totals = proposed_totals


def _build_rook_neighbors() -> tuple[tuple[int, ...], ...]:
    """Build row-major rook neighbors in down/up/right/left order for reproducible summation."""
    neighbors = []

    for node in range(GRID_NODE_COUNT):
        row, column = divmod(node, GRID_SIDE_LENGTH)
        adjacent_nodes = []

        for row_step, column_step in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            adjacent_row, adjacent_column = row + row_step, column + column_step

            if 0 <= adjacent_row < GRID_SIDE_LENGTH and 0 <= adjacent_column < GRID_SIDE_LENGTH:
                adjacent_nodes.append(adjacent_row * GRID_SIDE_LENGTH + adjacent_column)

        neighbors.append(tuple(adjacent_nodes))

    return tuple(neighbors)
