"""Population multiset preservation across share arrangements."""

import numpy as np
from experiments.grid_configurations.grid_pop_share_arrangements import (
    Arrangement,
    arrange_shares,
    build_population_share_distributions,
)


def test_share_arrangements_preserve_population_multisets():
    for shares in build_population_share_distributions().values():
        original = shares.copy()
        for arrangement in Arrangement:
            grid = arrange_shares(shares, arrangement, np.random.default_rng(7))
            np.testing.assert_array_equal(np.sort(grid.ravel()), np.sort(shares))
        np.testing.assert_array_equal(shares, original)
