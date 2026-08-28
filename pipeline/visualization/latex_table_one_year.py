"""Generate a ranked LaTeX table from a tracts_in_cbsa metrics CSV."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd

from pipeline.process_results import enrich_metrics
from pipeline.utils.visualization_settings import _short_name

# ── configuration ─────────────────────────────────────────────────────────────

# Input CSV (relative to repo root, where the script is invoked from).
INPUT_CSV = Path("outputs/tracts_in_cbsa/white_black.csv")

RANK_BY = "area_title" #"total_population" # any metric column, or "area_title" for alphabetical order
# Set to None to derive from COLUMNS (or fall back to the raw column name).
RANK_LABEL = "population size"  # None to auto; ignored when RANK_BY = "area_title"
RANK_ASCENDING = True # or False; set True for ascending / A to Z when sorting alphabetically

# ── alphabetical variant (uncomment to use) ───────────────────────────────────
# RANK_BY        = "area_title"
# RANK_LABEL     = None
# RANK_ASCENDING = True
TOP_N = 100

# Year filter, set to None to include all decades.
YEAR_FILTER = 2020  # e.g. 1980 | 1990 | 2000 | 2010 | 2020 | None

# Columns to show. Keys are CSV column names, values are
# the LaTeX column headers printed in the table.
COLUMNS = {"half_edge_1": r"Capy ($\lambda=1$)",
    "moran_P": r"Moran's I (P)",
    "dissimilarity_1": "Dissimilarity",
    "total_population": "Population"
    }

DECIMAL_PLACES = 3

# Per-column decimal overrides.  Any column not listed here uses DECIMAL_PLACES.
# Use 0 for integer-valued columns (a thousands separator is added automatically).
COLUMN_DECIMALS: dict[str, int] = {"total_population": 0}

# Output path. Set to None to auto-generate from INPUT_CSV / RANK_BY / YEAR_FILTER.
OUTPUT_TEX: Path | None = None

# ── helpers ───────────────────────────────────────────────────────────────────

def _escape_latex(text: str) -> str:
    """Escape special LaTeX characters in a plain-text string."""
    replacements = {
        "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
        "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}", "\\": r"\textbackslash{}"}
    for char, escaped in replacements.items():
        text = text.replace(char, escaped)
    return text


def _auto_output_path(input_csv: Path, rank_by: str, year: int | None, n: int) -> Path:
    stem = input_csv.stem
    year_tag = f"_{year}" if year is not None else "_all_years"
    return input_csv.parent / f"latex_tables/{stem}_table_{rank_by}{year_tag}_top{n}.tex"


def build_table(input_csv: Path = INPUT_CSV, rank_by: str = RANK_BY, rank_label: str | None = RANK_LABEL, rank_ascending: bool = RANK_ASCENDING, top_n: int = TOP_N, year_filter: int | None = YEAR_FILTER, columns: dict[str, str] = COLUMNS, decimal_places: int = DECIMAL_PLACES, column_decimals: dict[str, int] = COLUMN_DECIMALS, output_tex: Path | None = OUTPUT_TEX) -> Path:

    df = enrich_metrics(pd.read_csv(input_csv))
    if year_filter is not None:
        df = df[df["year"] == year_filter].copy()

    df = (df.sort_values(rank_by, ascending=rank_ascending)
          .head(top_n)
          .reset_index(drop=True))
    df.insert(0, "rank", range(1, len(df) + 1))

    metric_cols = list(columns.keys())
    missing = [c for c in metric_cols + [rank_by] if c not in df.columns]
    if missing:
        raise ValueError(f"Column(s) not found in data: {missing}\n"
            f"Available columns: {list(df.columns)}")

    display = df[["rank", "area_title"] + metric_cols].copy()
    display["area_title"] = display["area_title"].apply(_short_name)
    display.rename(columns={"rank": "Rank", "area_title": "Metro Area"}, inplace=True)

    # ── format numbers ─────────────────────────────────────────────────────────
    for col in metric_cols:
        dp = column_decimals.get(col, decimal_places)
        fmt = f"{{:,.{dp}f}}"  # thousands separator is a no-op for values < 1000
        display[col] = display[col].apply(
            lambda v, f=fmt: f.format(v) if pd.notna(v) else "---"
        )

    # ── build LaTeX ────────────────────────────────────────────────────────────
    col_headers = ["Rank", "Metro Area"] + list(columns.values())
    n_cols = len(col_headers)
    col_spec = "r" + "l" + "r" * (n_cols - 2)  # rank | metro area | metrics

    year_note = str(year_filter) if year_filter is not None else "all years"
    pair_label = "White--Black" if "black" in input_csv.stem.lower() else input_csv.stem
    if rank_by == "area_title":
        caption = f"{top_n} CBSAs ({pair_label}), sorted alphabetically ({year_note})."
    else:
        rank_label = rank_label or columns.get(rank_by, rank_by)
        direction = "lowest" if rank_ascending else "highest"
        caption = (
            f"Top {top_n} CBSAs by {direction} {rank_label} ({year_note}), "
            f"{pair_label}."
        )

    lines = [
        r"\begin{table}[htbp]",
        r"  \centering",
        f"  \\caption{{{caption}}}",
        f"  \\label{{tab:{input_csv.stem}_{rank_by}_{year_note.replace(' ', '_')}}}",
        f"  \\begin{{tabular}}{{{col_spec}}}",
        r"    \toprule",
    ]

    # Header row
    header_cells = " & ".join(f"\\textbf{{{h}}}" for h in col_headers)
    lines.append(f"    {header_cells} \\\\")
    lines.append(r"    \midrule")

    # Data rows
    for _, row in display.iterrows():
        cells = [_escape_latex(str(v)) for v in row.tolist()]
        lines.append(f"    {' & '.join(cells)} \\\\")

    lines += [
        r"    \bottomrule",
        r"  \end{tabular}",
        r"\end{table}"]

    latex = "\n".join(lines) + "\n"

    # ── save ───────────────────────────────────────────────────────────────────
    out = output_tex or _auto_output_path(input_csv, rank_by, year_filter, top_n)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(latex)
    print(f"Saved to {out}")
    return out


if __name__ == "__main__":
    build_table()
