"""Generate a wide ranked LaTeX table: one CBSA per row, metrics repeated by decade."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd

from pipeline.process_results import enrich_metrics
from pipeline.utils.visualization_settings import _short_name

# ── configuration ─────────────────────────────────────────────────────────────

# Input CSV (relative to repo root, where the script is invoked from).
INPUT_CSV = Path("outputs/tracts_in_cbsa/white_black.csv")

# Decades to show as column groups (left → right).
YEARS = [1990, 2000, 2010, 2020]

# Column to rank by, and which year's value of that column to use for sorting.
# Use "area_title" to sort alphabetically (RANK_YEAR is ignored in that case).
RANK_BY   = "half_edge_1"
RANK_YEAR = 2020   # must be in YEARS (or any year present in the data)
RANK_LABEL: str | None = None  # None → auto-derive from COLUMNS or raw name
RANK_ASCENDING = False

# ── alphabetical variant (uncomment to use) ───────────────────────────────────
RANK_BY        = "area_title"
RANK_LABEL     = None
RANK_ASCENDING = True

TOP_N = 100

# Metric columns to show in each decade group.
# Keys are CSV column names, values are the short LaTeX headers (year appended automatically).
COLUMNS = {
    "half_edge_1":    "HE",
    "moran_P":        r"$I$",
    "dissimilarity_1": "$D$"
}

DECIMAL_PLACES = 3

# Output path. None to auto-generate from INPUT_CSV / RANK_BY / RANK_YEAR.
OUTPUT_TEX: Path | None = None

# ── helpers ───────────────────────────────────────────────────────────────────

def _escape_latex(text: str) -> str:
    """Escape special LaTeX characters in a plain-text string."""
    replacements = {
        "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
        "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}", "\\": r"\textbackslash{}",
    }
    for char, escaped in replacements.items():
        text = text.replace(char, escaped)
    return text


def _auto_output_path(input_csv: Path, rank_by: str, rank_year: int, n: int) -> Path:
    stem = input_csv.stem
    return input_csv.parent / f"latex_tables/{stem}_table_{rank_by}_{rank_year}_top{n}_all_years.tex"


def build_table(
    input_csv: Path = INPUT_CSV,
    years: list[int] = YEARS,
    rank_by: str = RANK_BY,
    rank_year: int = RANK_YEAR,
    rank_label: str | None = RANK_LABEL,
    rank_ascending: bool = RANK_ASCENDING,
    top_n: int = TOP_N,
    columns: dict[str, str] = COLUMNS,
    decimal_places: int = DECIMAL_PLACES,
    output_tex: Path | None = OUTPUT_TEX,
) -> Path:
    metric_cols = list(columns.keys())

    # ── load, enrich, pivot ────────────────────────────────────────────────────
    df = enrich_metrics(pd.read_csv(input_csv))

    # Keep one area_title per area_code (stable across years).
    names = df.groupby("area_code")["area_title"].first()

    # Pivot: index = area_code, columns = MultiIndex(metric, year).
    # Only keep the requested years before pivoting to avoid stray columns.
    df_years = df[df["year"].isin(years)]
    wide = df_years.pivot(index="area_code", columns="year", values=metric_cols)
    # Flatten MultiIndex → "half_edge_1_2020", "moran_P_2020", …
    wide.columns = [f"{col}_{yr}" for col, yr in wide.columns]
    wide = names.to_frame().join(wide)

    # ── validate ───────────────────────────────────────────────────────────────
    expected = [f"{m}_{yr}" for yr in years for m in metric_cols]
    if rank_by == "area_title":
        sort_col = "area_title"
        missing = [c for c in expected if c not in wide.columns]
    else:
        sort_col = f"{rank_by}_{rank_year}"
        missing = [c for c in expected + [sort_col] if c not in wide.columns]
    if missing:
        raise ValueError(
            f"Column(s) not found after pivot: {missing}\n"
            f"Available: {list(wide.columns)}")

    # ── rank & subset ──────────────────────────────────────────────────────────
    wide = (
        wide.sort_values(sort_col, ascending=rank_ascending)
            .head(top_n)
            .reset_index(drop=True))
    wide.insert(0, "rank", range(1, len(wide) + 1))

    # ── build display DataFrame ────────────────────────────────────────────────
    # Column order: rank, area_title, then for each year all metrics.
    ordered_metric_cols = [f"{m}_{yr}" for yr in years for m in metric_cols]
    display = wide[["rank", "area_title"] + ordered_metric_cols].copy()
    display["area_title"] = display["area_title"].apply(_short_name)
    display.rename(columns={"rank": "Rank", "area_title": "Metro Area"}, inplace=True)

    # Format numbers.
    fmt = f"{{:.{decimal_places}f}}"
    for col in ordered_metric_cols:
        display[col] = display[col].apply(
            lambda v: fmt.format(v) if pd.notna(v) else "---"
        )

    # ── build LaTeX ────────────────────────────────────────────────────────────
    year_short = {yr: f"'{str(yr)[2:]}" for yr in years}
    metric_headers = [
        f"{columns[m]} {year_short[yr]}" for yr in years for m in metric_cols
    ]
    col_headers = ["Rank", "Metro Area"] + metric_headers
    n_cols = len(col_headers)
    col_spec = "r" + "l" + "r" * (n_cols - 2)

    # Add a \cmidrule under each decade group to visually separate them.
    n_metrics = len(metric_cols)
    # Column indices are 1-based in LaTeX; Rank=1, Metro Area=2, then groups.
    cmidrules = []
    for i, _yr in enumerate(years):
        left  = 3 + i * n_metrics
        right = left + n_metrics - 1
        cmidrules.append(rf"    \cmidrule(lr){{{left}-{right}}}")

    pair_label  = "White--Black" if "black" in input_csv.stem.lower() else input_csv.stem
    years_str   = ", ".join(str(y) for y in years)
    if rank_by == "area_title":
        caption = f"{top_n} CBSAs ({pair_label}), sorted alphabetically; metrics for {years_str}."
    else:
        rank_label_str = rank_label or columns.get(rank_by, rank_by)
        direction = "lowest" if rank_ascending else "highest"
        caption = (
            f"Top {top_n} CBSAs ranked by {direction} {rank_label_str} in {rank_year} "
            f"({pair_label}), metrics shown for {years_str}."
        )

    lines = [
        r"\begin{table}[htbp]",
        r"  \centering",
        f"  \\caption{{{caption}}}",
        f"  \\label{{tab:{input_csv.stem}_{rank_by}_{rank_year}_all_years}}",
        f"  \\begin{{tabular}}{{{col_spec}}}",
        r"    \toprule"]

    # Header row with cmidrules under each year group.
    header_cells = " & ".join(f"\\textbf{{{h}}}" for h in col_headers)
    lines.append(f"    {header_cells} \\\\")
    lines.extend(cmidrules)
    lines.append(r"    \midrule")

    # Data rows.
    for _, row in display.iterrows():
        cells = [_escape_latex(str(v)) for v in row.tolist()]
        lines.append(f"    {' & '.join(cells)} \\\\")

    lines += [
        r"    \bottomrule",
        r"  \end{tabular}",
        r"\end{table}"]

    latex = "\n".join(lines) + "\n"

    # ── save ───────────────────────────────────────────────────────────────────
    out = output_tex or _auto_output_path(input_csv, rank_by, rank_year, top_n)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(latex)
    print(f"Saved to {out}")
    return out


if __name__ == "__main__":
    build_table()
