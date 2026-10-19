"""Mass conservation and geometry of expanding-support diffusion."""

from itertools import pairwise

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from experiments.experiment_scores import calculate_experiment_scores
from experiments.grid_adjacency import build_grid_adjacency
from experiments.synthetic_diffusion import plot_expanding_support as plotting
from experiments.synthetic_diffusion.expanding_support import (
    Demography,
    SupportShape,
    build_expanding_support_masks,
    build_expanding_support_trajectories,
    run_expanding_support,
)
from experiments.synthetic_diffusion.plot_expanding_support import plot_expanding_support_trace


@pytest.mark.parametrize(
    "shape, initial_mass, growth_mass, decline_mass",
    [
        (SupportShape.CENTERED_RECTANGLE, 100, 160, 40),
        (SupportShape.ROOK_EXPANDING_CORE, 25, 40, 10),
        (SupportShape.THICK_CROSS, 99, 160, 40),
    ],
)
def test_expanding_populations_preserve_constant_mass_and_reach_demographic_endpoints(
    shape, initial_mass, growth_mass, decline_mass
):
    masks = build_expanding_support_masks()[shape]
    trajectories = build_expanding_support_trajectories(shape, masks)
    expected_final_mass = {
        Demography.CONSTANT: initial_mass,
        Demography.GROWTH: growth_mass,
        Demography.DECLINE: decline_mass,
    }

    assert [trajectory.demography for trajectory in trajectories] == list(Demography)

    for trajectory in trajectories:
        grids = trajectory.shares
        assert trajectory.shape == shape
        assert np.all((grids >= 0) & (grids <= 1))
        np.testing.assert_array_equal(grids > 0, masks)
        assert grids[0].sum() == initial_mass
        np.testing.assert_allclose(grids[-1], grids[-1, 0, 0])
        assert grids[-1].sum() == pytest.approx(expected_final_mass[trajectory.demography])

        if trajectory.demography == Demography.CONSTANT:
            np.testing.assert_allclose(grids.sum(axis=(1, 2)), initial_mass)


def test_rectangle_alternates_column_and_row_expansion():
    masks = build_expanding_support_masks()[SupportShape.CENTERED_RECTANGLE]
    expected_dimensions = (
        (10, 10),
        (10, 12),
        (12, 12),
        (12, 14),
        (14, 14),
        (14, 16),
        (16, 16),
        (16, 18),
        (18, 18),
        (18, 20),
        (20, 20),
    )
    assert len(masks) == len(expected_dimensions)

    for mask, (height, width) in zip(masks, expected_dimensions, strict=True):
        expected = np.zeros((20, 20), dtype=bool)
        top, left = (20 - height) // 2, (20 - width) // 2
        expected[top : top + height, left : left + width] = True
        np.testing.assert_array_equal(mask, expected)


@pytest.mark.parametrize("shape", [SupportShape.ROOK_EXPANDING_CORE, SupportShape.THICK_CROSS])
def test_rook_expansion_adds_exactly_the_horizontal_and_vertical_neighbors(shape):
    masks = build_expanding_support_masks()[shape]
    initial_mask = np.zeros((20, 20), dtype=bool)

    if shape == SupportShape.ROOK_EXPANDING_CORE:
        initial_mask[8:13, 8:13] = True
    else:
        initial_mask[1:19, 8:11] = True
        initial_mask[8:11, 1:19] = True

    np.testing.assert_array_equal(masks[0], initial_mask)
    assert masks[-1].all()
    assert not masks[-2].all()

    for previous, current in pairwise(masks):
        expanded = previous.copy()
        expanded[1:, :] |= previous[:-1, :]
        expanded[:-1, :] |= previous[1:, :]
        expanded[:, 1:] |= previous[:, :-1]
        expanded[:, :-1] |= previous[:, 1:]
        np.testing.assert_array_equal(current, expanded)


@pytest.mark.parametrize(
    "shape, first_expansion_fraction, demographic_progress, initial_share, growth_share, decline_share",
    [
        (SupportShape.CENTERED_RECTANGLE, 120 / 400, 1 / 10, 0.25, 0.4, 0.1),
        (SupportShape.ROOK_EXPANDING_CORE, 45 / 400, 1 / 16, 25 / 400, 0.1, 0.025),
        (SupportShape.THICK_CROSS, 167 / 400, 68 / 301, 99 / 400, 0.4, 0.1),
    ],
)
def test_intermediate_overall_share_uses_step_or_occupied_area_as_specified(
    shape,
    first_expansion_fraction,
    demographic_progress,
    initial_share,
    growth_share,
    decline_share,
):
    masks = build_expanding_support_masks()[shape]
    final_shares = {
        Demography.CONSTANT: initial_share,
        Demography.GROWTH: growth_share,
        Demography.DECLINE: decline_share,
    }

    for trajectory in build_expanding_support_trajectories(shape, masks):
        grid = trajectory.shares[1]
        expected_overall_share = initial_share + demographic_progress * (
            final_shares[trajectory.demography] - initial_share
        )
        assert grid.mean() == pytest.approx(expected_overall_share)
        np.testing.assert_allclose(
            grid[grid > 0], expected_overall_share / first_expansion_fraction
        )


def test_initial_rectangle_scores_match_known_values():
    rectangle = build_expanding_support_masks()[SupportShape.CENTERED_RECTANGLE][0]
    first_population = rectangle.astype(float).ravel()
    initial_scores = calculate_experiment_scores(
        build_grid_adjacency(20), first_population, 1 - first_population
    )
    assert initial_scores.metric_values["dissimilarity"] == pytest.approx(1)
    assert initial_scores.metric_values["capy"] == pytest.approx(0.9459154929577465)
    assert initial_scores.metric_values["moran_with_self"] == pytest.approx(11 / 12)
    assert initial_scores.metric_values["moran_row_standardized"] == pytest.approx(13 / 15)


def test_expanding_trace_uses_caller_axes_and_actual_line_handles():
    expanding_df = pd.DataFrame(
        [
            {"demography": demography, "support_fraction": step, "capy": value}
            for demography in ("constant", "growth", "decline")
            for step, value in ((0.25, 0.9), (1, 0.5))
        ]
    )
    figure, axes = plt.subplots()
    try:
        handles = plot_expanding_support_trace(axes, expanding_df, "capy", "support_fraction")
        assert len(handles) == 3
        assert all(handle in axes.lines for handle in handles)
    finally:
        plt.close(figure)


def test_expanding_support_saves_and_plots_each_shape_separately(tmp_path, monkeypatch):
    data_directory = tmp_path / "results"
    output_directory = tmp_path / "figures"
    run_expanding_support(data_directory)
    masks_by_shape = build_expanding_support_masks()
    shapes = set(masks_by_shape)
    assert {path.name for path in data_directory.iterdir()} == shapes

    for shape in shapes:
        shape_directory = data_directory / shape
        scores_df = pd.read_parquet(shape_directory / "expanding_support_scores.parquet")
        assert set(scores_df["shape"]) == {shape}

        with np.load(shape_directory / "states.npz") as saved:
            trajectories = build_expanding_support_trajectories(shape, masks_by_shape[shape])
            expected_names = {f"{shape}_{trajectory.demography}" for trajectory in trajectories}
            assert set(saved.files) == expected_names

            for trajectory in trajectories:
                np.testing.assert_array_equal(
                    saved[f"{shape}_{trajectory.demography}"], trajectory.shares
                )

    exports = []

    def record_export(figure, path):
        exports.append(path)
        plt.close(figure)

    monkeypatch.setattr(plotting, "save_plot", record_export)
    monkeypatch.setattr(plotting, "save_legend", lambda handles, path: exports.append(path))
    monkeypatch.setattr(plotting, "save_colorbar", lambda path, *args: exports.append(path))
    plotting.plot_expanding_support(data_directory, output_directory)
    assert {path.parent for path in exports} == {output_directory / shape for shape in shapes}

    assert len(exports) == len(set(exports))

    for shape in shapes:
        names = {path.name for path in exports if path.parent.name == shape}
        assert len(names) == 25
        assert {"demography_legend", "moran_conventions_legend", "share_colorbar"} <= names


def test_moran_comparison_uses_constant_trajectory_and_preserves_undefined_endpoint():
    scores_df = pd.DataFrame(
        {
            "demography": ["constant", "constant", "growth"],
            "support_fraction": [1.0, 0.25, 0.25],
            "moran_with_self": [np.nan, 0.9, 0.1],
            "moran_row_standardized": [np.nan, 0.8, 0.2],
        }
    )
    figure, axes = plt.subplots()

    try:
        axes.set_ylim(-0.5, 1.5)
        handles = plotting.plot_expanding_support_moran_comparison(
            axes, scores_df, "support_fraction"
        )
        assert len(handles) == 2
        assert all(handle in axes.lines for handle in handles)
        np.testing.assert_array_equal(handles[0].get_xdata(), [0.25, 1.0])
        np.testing.assert_allclose(handles[0].get_ydata(), [0.9, np.nan])
        np.testing.assert_allclose(handles[1].get_ydata(), [0.8, np.nan])
        assert axes.get_ylim() == (-0.5, 1.5)
    finally:
        plt.close(figure)
