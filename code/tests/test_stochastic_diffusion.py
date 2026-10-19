"""Complete stochastic traces, demographic calibration, population conservation, and rendering."""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from experiments.synthetic_diffusion import plot_stochastic_diffusion, stochastic_diffusion
from experiments.synthetic_diffusion.stochastic_diffusion import (
    SOURCE_METRICS,
    move_population,
    read_cached_stochastic_scores,
    run_stochastic_diffusion,
    simulate_early_snapshots,
)


def test_cached_stochastic_traces_exclude_entire_partial_replicates(tmp_path):
    source_directory = tmp_path / "scripts/synthetic/stochastic_data"
    source_directory.mkdir(parents=True)

    for number in (2, 3):
        rows = []

        for letter in "ABC":
            for step in [*range(801), 4000]:
                rows.append(
                    {
                        "variant": f"{number}{letter}",
                        "replicate": 0,
                        "step": step,
                        "rho": 0.25,
                        **dict.fromkeys(SOURCE_METRICS, 0.5),
                    }
                )

        rows.append(
            {
                "variant": f"{number}C",
                "replicate": 1,
                "step": 0,
                "rho": 0.25,
                **dict.fromkeys(SOURCE_METRICS, 0.9),
            }
        )
        pd.DataFrame(rows).to_csv(
            source_directory / f"stochastic_diffusion_{number}abc_long_scores.csv", index=False
        )

    scores_df, coverage_df = read_cached_stochastic_scores(tmp_path)
    assert len(scores_df) == 6 * 801
    assert scores_df.replicate.eq(0).all()
    assert coverage_df.included.sum() == 6
    assert coverage_df.loc[~coverage_df.included, "replicate"].tolist() == [1, 1]
    assert scores_df.demographic_horizon.eq(4000).all()


def test_early_growth_uses_long_run_demographic_calibration():
    snapshots = simulate_early_snapshots(False, "growth", 20260919)
    np.testing.assert_array_equal(
        snapshots[:, 1], np.broadcast_to(snapshots[0, 1], snapshots[:, 1].shape)
    )
    assert snapshots[0, 0].sum() == 100000
    assert snapshots[-1, 0].sum() == pytest.approx(100000 * 2 ** (800 / 4000), rel=0.01)
    assert np.issubdtype(snapshots.dtype, np.integer)


def test_particle_movement_conserves_counts_without_mutating_input():
    counts = np.array([100, 200, 300], dtype=np.int64)
    moved = move_population(
        counts, [np.array([1]), np.array([0, 2]), np.array([1])], np.random.default_rng(17)
    )
    assert moved.sum() == counts.sum()
    assert np.issubdtype(moved.dtype, np.integer)
    assert (moved >= 0).all()
    np.testing.assert_array_equal(counts, [100, 200, 300])


def test_stochastic_preparation_saves_quantiles_and_snapshot_coordinates(tmp_path, monkeypatch):
    scores_df = pd.DataFrame(
        [
            {
                "movement": movement,
                "demography": demography,
                "step": step,
                **dict.fromkeys(SOURCE_METRICS.values(), value),
            }
            for movement in ("one_sided", "two_sided")
            for demography in ("constant", "growth", "decline")
            for step in (0, 2)
            for value in (0.2, 0.8)
        ]
    )
    monkeypatch.setattr(
        stochastic_diffusion,
        "read_cached_stochastic_scores",
        lambda *_: (
            scores_df,
            pd.DataFrame({"movement": ["one_sided", "two_sided"], "included": [True, False]}),
        ),
    )
    monkeypatch.setattr(stochastic_diffusion, "SNAPSHOT_STEPS", (0, 2))
    monkeypatch.setattr(
        stochastic_diffusion, "simulate_early_snapshots", lambda *_: np.ones((2, 2, 2, 2))
    )
    run_stochastic_diffusion(tmp_path, tmp_path)
    assert {path.name for path in tmp_path.iterdir()} == {"one_sided", "two_sided"}

    for movement_rule in ("one_sided", "two_sided"):
        movement_directory = tmp_path / movement_rule
        saved_scores_df = pd.read_parquet(movement_directory / "stochastic_scores.parquet")
        summary_df = pd.read_parquet(movement_directory / "stochastic_trace_summary.parquet")
        coverage_df = pd.read_parquet(movement_directory / "source_replicate_coverage.parquet")
        assert set(saved_scores_df.movement) == {movement_rule}
        assert set(summary_df.movement) == {movement_rule}
        assert set(coverage_df.movement) == {movement_rule}
        assert coverage_df.included.tolist() == [movement_rule == "one_sided"]
        pd.testing.assert_frame_equal(
            saved_scores_df,
            scores_df.loc[scores_df.movement.eq(movement_rule)].reset_index(drop=True),
        )
        assert len(summary_df) == 3 * 2 * 3
        np.testing.assert_allclose(summary_df.loc[summary_df["quantile"].eq(0.1), "capy"], 0.26)
        np.testing.assert_allclose(summary_df.loc[summary_df["quantile"].eq(0.5), "capy"], 0.5)
        np.testing.assert_allclose(summary_df.loc[summary_df["quantile"].eq(0.9), "capy"], 0.74)

        with np.load(movement_directory / "stochastic_states.npz") as snapshots:
            assert set(snapshots.files) == {
                "snapshot_steps",
                *(
                    f"{movement_rule}_{demography}"
                    for demography in ("constant", "growth", "decline")
                ),
            }
            np.testing.assert_array_equal(snapshots["snapshot_steps"], [0, 2])

    # Rendering reads saved coordinates even after the simulation's selected steps change.
    monkeypatch.setattr(stochastic_diffusion, "SNAPSHOT_STEPS", (99, 100))
    paths = []

    def record_export(figure, path):
        paths.append(path)
        plt.close(figure)

    monkeypatch.setattr(plot_stochastic_diffusion, "save_plot", record_export)
    monkeypatch.setattr(
        plot_stochastic_diffusion, "save_legend", lambda handles, path: paths.append(path)
    )
    monkeypatch.setattr(
        plot_stochastic_diffusion, "save_colorbar", lambda path, *args: paths.append(path)
    )
    plot_stochastic_diffusion.plot_stochastic_diffusion(tmp_path, tmp_path)
    assert len(paths) == len(set(paths))
    assert {path.parent for path in paths} == {tmp_path / "one_sided", tmp_path / "two_sided"}

    for movement_rule in ("one_sided", "two_sided"):
        names = {path.name for path in paths if path.parent.name == movement_rule}
        assert f"002_share_diff_const_{movement_rule}_stoc" in names
        assert f"002_pop_diff_const_{movement_rule}_stoc" in names
        assert not any(name.startswith("099_") for name in names)
        assert {
            "demography_legend",
            "moran_conventions_legend",
            "share_colorbar",
            "population_colorbar",
        } <= names
