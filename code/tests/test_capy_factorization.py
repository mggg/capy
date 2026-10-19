"""Factorization, paired-swap invariants, and saved figure selection contracts."""

from dataclasses import asdict

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from experiments.grid_adjacency import build_grid_adjacency
from experiments.grid_configurations import plot_capy_factorization as factorization_plotting
from experiments.grid_configurations.capy_factorization import (
    EXAMPLE_SHARE_TARGETS,
    QUADRANT_CENTERS,
    calculate_factorization_scores,
    generate_factorization_sample,
    select_factorization_examples,
)
from experiments.grid_configurations.factorization_layout import (
    GRID_NODE_COUNT,
    GRID_SIDE_LENGTH,
    swap_toward_target_layout,
)
from experiments.grid_configurations.plot_capy_factorization import (
    FactorizationPanelStyle,
    build_faded_quadrant_colors,
    plot_capy_factorization,
    plot_factorization_examples,
    plot_factorization_gradients,
    plot_factorization_panels,
    read_factorization_plot_data,
)
from PIL import Image
from scipy import sparse


def test_factors_and_exposure_agree_with_dense_pair_weights():
    rng = np.random.default_rng(17)
    shares = rng.uniform(0.02, 0.98, GRID_NODE_COUNT)
    totals = rng.lognormal(4, 0.6, GRID_NODE_COUNT)

    result = calculate_factorization_scores(shares, totals)
    scores = result.comparison_scores.metric_values

    adjacency = build_grid_adjacency(GRID_SIDE_LENGTH)
    weights = (adjacency + sparse.eye_array(GRID_NODE_COUNT)).toarray()
    pair_weights = weights * np.outer(totals, totals)
    endpoint_weights = pair_weights.sum(axis=1) / pair_weights.sum()
    endpoint_share = endpoint_weights @ shares
    variance = endpoint_weights @ (shares - endpoint_share) ** 2
    covariance = (
        (shares - endpoint_share) @ pair_weights @ (shares - endpoint_share) / pair_weights.sum()
    )

    assert result.endpoint_share == pytest.approx(endpoint_share)
    assert result.intensity == pytest.approx(variance / (endpoint_share * (1 - endpoint_share)))
    assert result.layout == pytest.approx(covariance / variance)
    assert scores["capy_phi"] == pytest.approx(result.intensity * result.layout)
    assert scores["capy"] == pytest.approx((1 + result.intensity * result.layout) / 2)

    group, other = shares * totals, (1 - shares) * totals
    local_shares = (weights @ group) / (weights @ totals)

    assert scores["x_isolation"] == pytest.approx(np.average(local_shares, weights=group))
    assert scores["y_to_x_exposure"] == pytest.approx(np.average(local_shares, weights=other))


def test_swaps_preserve_paired_populations_and_recompute_layout():
    rng = np.random.default_rng(40)
    shares = rng.uniform(0.1, 0.9, GRID_NODE_COUNT)
    totals = rng.lognormal(4, 0.6, GRID_NODE_COUNT)
    original_shares, original_totals = shares.copy(), totals.copy()
    before = calculate_factorization_scores(shares, totals)

    swapped_shares, swapped_totals, estimated_layout = swap_toward_target_layout(
        shares, totals, 0.6, rng, steps=300
    )

    original_pairs = np.column_stack((shares, totals))[np.argsort(totals)]
    swapped_pairs = np.column_stack((swapped_shares, swapped_totals))[np.argsort(swapped_totals)]
    np.testing.assert_allclose(swapped_pairs, original_pairs, rtol=0, atol=1e-15)
    np.testing.assert_array_equal(shares, original_shares)
    np.testing.assert_array_equal(totals, original_totals)

    after = calculate_factorization_scores(swapped_shares, swapped_totals)

    assert after.layout == pytest.approx(estimated_layout, abs=1e-12)
    assert after.comparison_scores.group_share == pytest.approx(
        before.comparison_scores.group_share
    )

    for metric in ("dissimilarity", "entropy_index", "relative_diversity"):
        assert after.comparison_scores.metric_values[metric] == pytest.approx(
            before.comparison_scores.metric_values[metric]
        )


def test_seeded_sample_matches_known_grid_scores():
    first = generate_factorization_sample(0)
    second = generate_factorization_sample(0)

    assert first is not None and second is not None
    np.testing.assert_array_equal(first.shares, second.shares)
    np.testing.assert_array_equal(first.total_population, second.total_population)
    assert first.scores.comparison_scores.group_share == pytest.approx(0.20226529217063602)
    assert first.scores.comparison_scores.metric_values["capy"] == pytest.approx(
        0.40638213789856337
    )
    assert first.scores.layout == pytest.approx(-0.22957474106860978)
    assert abs(first.scores.layout - first.target_layout) <= 0.03


def test_selection_uses_quadrant_centers_and_seed_tiebreaks():
    rows = []

    for intensity, layout in QUADRANT_CENTERS.values():
        for share in EXAMPLE_SHARE_TARGETS:
            for _ in range(11):
                rows.append(
                    {
                        "seed": len(rows),
                        "intensity": intensity,
                        "layout": layout,
                        "group_share": share,
                    }
                )

    scores_df = pd.DataFrame(rows)

    selections = select_factorization_examples(scores_df.iloc[::-1])
    selections_df = pd.DataFrame([asdict(example) for example in selections])

    assert len(selections_df) == 160
    assert len(selections_df.loc[selections_df["rank"].eq(1)]) == 16
    assert selections_df.seed.tolist()[:10] == list(range(10))

    selected_df = selections_df.merge(scores_df, on="seed")

    for quadrant, (intensity, layout) in QUADRANT_CENTERS.items():
        quadrant_df = selected_df.loc[selected_df.quadrant.eq(quadrant)]

        assert quadrant_df.intensity.eq(intensity).all()
        assert quadrant_df.layout.eq(layout).all()

    with pytest.raises(ValueError, match="No accepted grids"):
        select_factorization_examples(scores_df.loc[scores_df.group_share.eq(0.45)])


@pytest.fixture
def saved_example_directory(tmp_path):
    """Save two contrasting grids with score and archive rows deliberately out of order."""
    data_directory = tmp_path / "results"
    data_directory.mkdir()

    pd.DataFrame(
        {
            "seed": [8, 3],
            "target_group_share": [0.4, 0.1],
            "group_share": [0.8, 0.2],
        }
    ).to_parquet(data_directory / "factorization_scores.parquet", index=False)

    pd.DataFrame(
        {
            "seed": [3, 8],
            "quadrant": ["weak_clustered", "strong_dispersed"],
            "target_group_share": [0.09, 0.45],
            "rank": [1, 1],
        }
    ).to_parquet(data_directory / "selected_examples.parquet", index=False)

    np.savez_compressed(
        data_directory / "grids.npz",
        seed=[3, 8],
        shares=np.stack([np.full((16, 16), 0.2), np.full((16, 16), 0.8)]),
        allow_pickle=False,
    )

    return data_directory


def test_saved_examples_match_by_seed_and_render_distinct_grids(saved_example_directory, tmp_path):
    plot_data = read_factorization_plot_data(saved_example_directory)

    assert plot_data.selected_scores_df.seed.tolist() == [3, 8]
    assert plot_data.selected_scores_df.group_share.tolist() == [0.2, 0.8]
    assert plot_data.selected_scores_df.target_group_share.tolist() == [0.09, 0.45]

    output_directory = tmp_path / "figures"
    plot_factorization_examples(plot_data.example_grids, output_directory)

    expected_files = {"weak_clustered_share_09.png", "strong_dispersed_share_45.png"}
    assert {path.name for path in output_directory.iterdir()} == expected_files

    with (
        Image.open(output_directory / "weak_clustered_share_09.png") as light_grid,
        Image.open(output_directory / "strong_dispersed_share_45.png") as dark_grid,
    ):
        assert light_grid.info["dpi"] == pytest.approx((300, 300), abs=0.01)
        assert dark_grid.info["dpi"] == pytest.approx((300, 300), abs=0.01)

        center = (light_grid.height // 2, light_grid.width // 2)
        assert np.asarray(light_grid)[center][:3].min() > 200
        assert np.asarray(dark_grid)[center][:3].max() < 100

        for grid in (light_grid, dark_grid):
            pixels = np.asarray(grid)[:, :, :3]
            assert np.all(pixels.max(axis=2) == pixels.min(axis=2))


@pytest.mark.parametrize(
    "seeds,shape,message",
    [
        ([3, 99], (2, 16, 16), "Grid archive seeds must match"),
        ([3, 8], (1, 16, 16), "one 16×16 share grid per seed"),
    ],
)
def test_mismatched_archive_fails_before_drawing(
    saved_example_directory, tmp_path, seeds, shape, message
):
    np.savez_compressed(
        saved_example_directory / "grids.npz",
        seed=seeds,
        shares=np.zeros(shape),
        allow_pickle=False,
    )
    output_directory = tmp_path / "figures"

    with pytest.raises(ValueError, match=message):
        plot_capy_factorization(saved_example_directory, output_directory)

    assert not output_directory.exists()


def test_missing_selection_column_raises_documented_key_error(saved_example_directory):
    selection_path = saved_example_directory / "selected_examples.parquet"
    selections_df = pd.read_parquet(selection_path)
    selections_df.drop(columns="target_group_share").to_parquet(selection_path, index=False)

    with pytest.raises(KeyError, match="target_group_share"):
        read_factorization_plot_data(saved_example_directory)

    with pytest.raises(KeyError, match="group_share"):
        select_factorization_examples(pd.DataFrame({"seed": [3]}))


def test_quadrant_fade_matches_original_cielab_colors_near_seams():
    intensity = np.array([0.46, 0.54, 0.46, 0.54])
    layout = np.array([0.24, 0.24, 0.16, 0.16])
    expected_colors = np.array(
        [
            [0.800284757921, 0.879422256417, 0.877101514909],
            [1, 0.820514193083, 0.778506272194],
            [0.899116284577, 0.955231187912, 0.986553044326],
            [1, 0.938192951808, 0.802384165488],
        ]
    )

    np.testing.assert_allclose(
        build_faded_quadrant_colors(intensity, layout), expected_colors, rtol=0, atol=1e-10
    )


@pytest.mark.parametrize(
    "panel_style,capy_limits,marker_size,edge_width,edge_opacity",
    [
        (FactorizationPanelStyle.ALL_GRIDS, (0.2, 1), 4, 0.2, 0.25),
        (FactorizationPanelStyle.SELECTED_TARGETS, (0.38, 0.77), 34, 0.5, 0.6),
        (FactorizationPanelStyle.GRADIENT, (0.2, 1), 2.5, 0, 0),
        (FactorizationPanelStyle.EXPOSURE_COMPARISON, (0.2, 1), 4, 0.2, 0.25),
    ],
)
def test_panel_families_preserve_original_scales_and_marker_appearance(
    monkeypatch, tmp_path, panel_style, capy_limits, marker_size, edge_width, edge_opacity
):
    scores_df = pd.DataFrame(
        {
            "intensity": [0.25, 0.75],
            "layout": [0.6, -0.2],
            "group_share": [0.1, 0.5],
            "capy": [0.5, 0.7],
        }
    )
    figures = []
    monkeypatch.setattr(
        factorization_plotting, "save_plot", lambda figure, _: figures.append(figure)
    )

    try:
        plot_factorization_panels(
            scores_df,
            np.array([[0, 0.5, 0.5], [1, 0.75, 0]]),
            tmp_path,
            panel_style=panel_style,
            metrics=("capy",),
        )
        score_axes = figures[1].axes[0]
        scatter = score_axes.collections[0]
        expected_opacity = 0.8 if panel_style is FactorizationPanelStyle.GRADIENT else 1

        assert score_axes.get_xlim() == (0, 0.52)
        assert score_axes.get_ylim() == capy_limits
        assert scatter.get_sizes() == pytest.approx([marker_size])
        assert scatter.get_linewidths() == pytest.approx([edge_width])
        assert scatter.get_edgecolors()[0, 3] == pytest.approx(edge_opacity)
        assert scatter.get_facecolors()[:, 3] == pytest.approx([expected_opacity] * 2)
        assert all(spine.get_visible() for spine in score_axes.spines.values())
        assert not any(line.get_visible() for line in score_axes.get_xgridlines())
        assert [tick.get_text() for tick in score_axes.get_xticklabels()] == ["0", ".25", ".5"]

        plot_bounds = score_axes.get_window_extent()

        if panel_style is FactorizationPanelStyle.GRADIENT:
            expected_ratio = 1.287 / 2.736
        elif panel_style is FactorizationPanelStyle.EXPOSURE_COMPARISON:
            expected_ratio = 1.535 / 3.696
        else:
            expected_ratio = 1.311 / 3.696

        assert plot_bounds.width / plot_bounds.height == pytest.approx(expected_ratio)
    finally:
        for figure in figures:
            plt.close(figure)


def test_gradient_colorbars_render_narrow_at_300_dpi(monkeypatch, tmp_path):
    scores_df = pd.DataFrame({"intensity": [0, 1], "layout": [-0.6, 1]})
    monkeypatch.setattr(
        factorization_plotting, "plot_factorization_panels", lambda *args, **kwargs: None
    )

    plot_factorization_gradients(scores_df, tmp_path)

    for factor in ("intensity", "layout"):
        with Image.open(tmp_path / f"{factor}_colorbar.png") as colorbar:
            pixels = np.asarray(colorbar)[:, :, :3].astype(int)
            colored = pixels.max(axis=2) - pixels.min(axis=2) > 30
            rows, columns = np.nonzero(colored)
            aspect_ratio = (rows.max() - rows.min() + 1) / (columns.max() - columns.min() + 1)

            # The black outline slightly reduces the interior colored region's width.
            assert 18 < aspect_ratio < 23
            assert colorbar.info["dpi"] == pytest.approx((300, 300), abs=0.01)
