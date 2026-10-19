"""Scientific invariants and export contracts for independent figure workflows."""

import pandas as pd
import pytest
from national_figures.prepare_national_results import select_complete_histories
from PIL import Image
from plotting.figure_style import create_plot, save_plot


def test_histories_exclude_missing_years_and_undefined_values():
    scores_df = pd.DataFrame(
        {
            "study_area_id": ["a", "a", "b", "b", "c"],
            "census_year": [1980, 2020, 1980, 2020, 2020],
            "value": [0.2, 0.4, 0.5, None, 0.7],
        }
    )
    assert select_complete_histories(scores_df, [1980, 2020]).study_area_id.tolist() == ["a", "a"]
    assert select_complete_histories(scores_df, [1980, 2000, 2020]).empty

    with pytest.raises(ValueError, match="one score"):
        select_complete_histories(pd.concat([scores_df, scores_df.iloc[:1]]), [1980, 2020])


def test_single_panel_export_removes_labels_and_titles_but_keeps_numeric_ticks(tmp_path):
    figure, axes = create_plot()
    axes.plot([0, 1], [1, 0], label="line")
    axes.set(xlabel="remove", ylabel="remove", title="remove", xticks=[0, 1])
    axes.legend()
    save_plot(figure, tmp_path / "panel")
    assert axes.get_xlabel() == axes.get_ylabel() == axes.get_title() == ""
    assert axes.get_legend() is None
    assert len(axes.get_xticklabels()) == 2
    assert not (tmp_path / "panel.pdf").exists()

    with Image.open(tmp_path / "panel.png") as panel_image:
        assert panel_image.size == (1020, 1020)
        assert panel_image.info["dpi"] == pytest.approx((300, 300), abs=0.01)
