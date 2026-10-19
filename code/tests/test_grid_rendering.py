"""Grid snapshots retain every cell boundary in the exported raster."""

import matplotlib.pyplot as plt
import numpy as np
import pytest
from plotting.figure_style import create_plot
from plotting.grids import plot_grid


@pytest.mark.parametrize("shape", [(20, 20), (12, 24)])
def test_every_internal_cell_boundary_is_visible(shape):
    figure, axes = create_plot()
    figure.set_dpi(300)
    plot_grid(axes, np.ones(shape))
    figure.canvas.draw()
    pixels = np.asarray(figure.canvas.buffer_rgba())

    try:
        boundaries = [(column - 0.5, 0) for column in range(1, shape[1])]
        boundaries += [(0, row - 0.5) for row in range(1, shape[0])]

        for boundary in boundaries:
            x, y = np.rint(axes.transData.transform(boundary)).astype(int)
            row = pixels.shape[0] - 1 - y
            # White boundaries add red to the otherwise zero-red teal cells.
            assert pixels[row - 2 : row + 3, x - 2 : x + 3, 0].max() > 30, boundary
    finally:
        plt.close(figure)
