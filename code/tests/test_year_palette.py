"""Check fixed and base-color year palettes in an isolated copy of shared styling."""

import re
import runpy
from pathlib import Path

import numpy as np
import pytest
from matplotlib.colors import to_rgb
from plotting import figure_style


@pytest.mark.parametrize("base_color", [None, figure_style.AMBER, figure_style.PURPLE_HEART])
def test_year_palette_keeps_year_order_and_dark_to_light_shades(tmp_path, base_color):
    # Exercise the source setting as a user would edit it, without changing imported styling.
    style_source = Path(figure_style.__file__).read_text()
    configured_source = re.sub(
        r"^YEAR_BASE_COLOR: str \| None = .+$",
        f"YEAR_BASE_COLOR: str | None = {base_color!r}",
        style_source,
        flags=re.MULTILINE,
    )
    configured_style_path = tmp_path / "figure_style.py"
    configured_style_path.write_text(configured_source)
    settings = runpy.run_path(str(configured_style_path))
    palette = settings["YEAR_COLORS"]

    assert list(palette) == [1980, 1990, 2000, 2010, 2020]

    if base_color is None:
        # The fixed palette is a user-editable styling choice.
        assert all(len(to_rgb(color)) == 3 for color in palette.values())
        return

    shades = np.array([to_rgb(color) for color in palette.values()])
    assert np.all(np.diff(shades.mean(axis=1)) > 0)
    assert np.allclose(shades[2], to_rgb(base_color), atol=1 / 255)
    assert shades[0].mean() > 0
    assert shades[-1].mean() < 1
