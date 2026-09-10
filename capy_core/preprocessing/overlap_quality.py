"""
Quality analysis for overlap assignments produced by overlaps.py.

For each (census_geography_type, study_area_type) combination present in the
clipped_geographies directory the script reports:
  - Distribution of unit counts per study area
  - Critically small study areas (< critical_threshold units)
  - Breakdown by census year
  - Breakdown by state (via STATEFP)
  - Missing study areas — definition files that produced no clipped output

Writes a single self-contained HTML report.

Run directly:
    poetry run python capy_core/preprocessing/overlap_quality.py [OPTIONS]
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import base64
import datetime
import io
import re
from typing import Optional

import fiona
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import typer
import tqdm as tqdm_module


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Matches clipped files produced by overlaps.py, e.g.:
#   tracts_in_cbsa_10180_2020_march_2020_vintage.gpkg
CLIPPED_RE = re.compile(
    r"^(tracts|block_groups|blocks|counties)"
    r"_in_(cbsa|county|max_city|max_county)"
    r"_(\d+)_(\d{4})_(.+)_vintage\.gpkg$"
)

# Matches study area definition files, e.g.: cbsa_10180_march_2020.gpkg
DEF_RE = re.compile(r"^(cbsa|county|max_city|max_county)_(\d+)_(.+)\.gpkg$")

# All six combinations this report covers (even if data are absent for some)
ALL_COMBOS = [
    ("tracts",       "cbsa"),
    ("block_groups", "cbsa"),
    ("blocks",       "cbsa"),
    ("tracts",       "max_city"),
    ("block_groups", "max_city"),
    ("blocks",       "max_city"),
]

STATEFP_TO_NAME: dict[str, str] = {
    "01": "Alabama",             "02": "Alaska",          "04": "Arizona",
    "05": "Arkansas",            "06": "California",      "08": "Colorado",
    "09": "Connecticut",         "10": "Delaware",        "11": "D.C.",
    "12": "Florida",             "13": "Georgia",         "15": "Hawaii",
    "16": "Idaho",               "17": "Illinois",        "18": "Indiana",
    "19": "Iowa",                "20": "Kansas",          "21": "Kentucky",
    "22": "Louisiana",           "23": "Maine",           "24": "Maryland",
    "25": "Massachusetts",       "26": "Michigan",        "27": "Minnesota",
    "28": "Mississippi",         "29": "Missouri",        "30": "Montana",
    "31": "Nebraska",            "32": "Nevada",          "33": "New Hampshire",
    "34": "New Jersey",          "35": "New Mexico",      "36": "New York",
    "37": "North Carolina",      "38": "North Dakota",    "39": "Ohio",
    "40": "Oklahoma",            "41": "Oregon",          "42": "Pennsylvania",
    "44": "Rhode Island",        "45": "South Carolina",  "46": "South Dakota",
    "47": "Tennessee",           "48": "Texas",           "49": "Utah",
    "50": "Vermont",             "51": "Virginia",        "53": "Washington",
    "54": "West Virginia",       "55": "Wisconsin",       "56": "Wyoming",
    "60": "American Samoa",      "66": "Guam",            "69": "N. Mariana Islands",
    "72": "Puerto Rico",         "78": "U.S. Virgin Islands",
}

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
       background: #f5f5f5; color: #333; font-size: 14px; line-height: 1.5; }
.container { max-width: 1200px; margin: 0 auto; padding: 24px; }
h1 { font-size: 24px; margin-bottom: 4px; color: #1a1a2e; }
.subtitle { color: #666; margin-bottom: 32px; font-size: 13px; }
h2 { font-size: 18px; margin: 32px 0 12px; color: #1a1a2e;
     padding-bottom: 6px; border-bottom: 2px solid #4e79a7; }
h3 { font-size: 15px; margin: 20px 0 8px; color: #555; }
.toc { background: white; border-radius: 8px; padding: 16px 24px; margin-bottom: 32px;
       box-shadow: 0 1px 4px rgba(0,0,0,.08); }
.toc ul { list-style: none; }
.toc li { margin: 4px 0; }
.toc a { color: #4e79a7; text-decoration: none; }
.toc a:hover { text-decoration: underline; }
.combo-section { background: white; border-radius: 8px; padding: 24px;
                 margin-bottom: 32px; box-shadow: 0 1px 4px rgba(0,0,0,.08); }
.stats-grid { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 20px; }
.stat-card { background: #f8f9fa; border-radius: 6px; padding: 12px 18px; min-width: 130px; }
.stat-card .label { font-size: 11px; color: #888; text-transform: uppercase; letter-spacing: .5px; }
.stat-card .value { font-size: 22px; font-weight: 600; color: #1a1a2e; }
.stat-card.warn .value { color: #e15759; }
table { width: 100%; border-collapse: collapse; margin: 8px 0 16px; font-size: 13px; }
th { background: #4e79a7; color: white; text-align: left;
     padding: 7px 10px; font-weight: 500; }
td { padding: 6px 10px; border-bottom: 1px solid #eee; }
tr:hover td { background: #f8f9fa; }
td.critical { color: #e15759; font-weight: 600; }
td.warn { color: #e65100; font-weight: 600; }
.chart-wrap { margin-bottom: 16px; }
.chart-wrap img { border-radius: 6px; max-width: 100%; }
.note { font-size: 12px; color: #888; margin-top: 6px; font-style: italic; }
.badge { display: inline-block; border-radius: 3px; padding: 1px 6px;
         font-size: 11px; font-weight: 600; }
.badge-ok   { background: #e8f5e9; color: #2e7d32; }
.badge-warn { background: #fff3e0; color: #e65100; }
.badge-none { background: #eeeeee; color: #757575; }
.empty-note { padding: 12px 16px; background: #f8f9fa; border-radius: 6px;
              color: #888; font-style: italic; font-size: 13px; }
"""


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

def _read_file_stats(path: Path) -> dict:
    """Return row count and unique STATEFP values for a gpkg file."""
    with fiona.open(path) as src:
        count = len(src)
        states: set[str] = set()
        for feature in src:
            fp = feature["properties"].get("STATEFP")
            if fp is not None:
                states.add(str(fp).zfill(2))
    return {"count": count, "states": sorted(states)}


def _collect_clipped_records(
    clipped_dir: Path,
    geo_type_filter: str,
    sa_type_filter: str,
) -> pd.DataFrame:
    """Scan clipped_dir recursively; return one record per matching gpkg file."""
    gpkg_files = sorted(clipped_dir.rglob("*.gpkg"))
    records = []
    for path in tqdm_module.tqdm(gpkg_files, desc="Reading clipped files", unit="file"):
        m = CLIPPED_RE.match(path.name)
        if not m:
            continue
        geo_type, sa_type, sa_id, year, vintage = m.groups()
        if geo_type_filter and geo_type != geo_type_filter:
            continue
        if sa_type_filter and sa_type != sa_type_filter:
            continue
        stats = _read_file_stats(path)
        records.append({
            "geo_type":   geo_type,
            "sa_type":    sa_type,
            "sa_id":      sa_id,
            "year":       year,
            "vintage":    vintage,
            "unit_count": stats["count"],
            "states":     stats["states"],   # list[str]
        })
    cols = ["geo_type", "sa_type", "sa_id", "year", "vintage", "unit_count", "states"]
    return pd.DataFrame(records, columns=cols) if records else pd.DataFrame(columns=cols)


def _collect_definitions(def_dir: Path) -> pd.DataFrame:
    """Return one record per study-area definition gpkg file."""
    records = []
    for path in sorted(def_dir.glob("*.gpkg")):
        m = DEF_RE.match(path.name)
        if not m:
            continue
        sa_type, sa_id, vintage = m.groups()
        records.append({"sa_type": sa_type, "sa_id": sa_id, "vintage": vintage})
    cols = ["sa_type", "sa_id", "vintage"]
    return pd.DataFrame(records, columns=cols) if records else pd.DataFrame(columns=cols)


# ---------------------------------------------------------------------------
# Chart helpers
# ---------------------------------------------------------------------------

def _fig_to_b64(fig: plt.Figure) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def _hist_b64(counts: pd.Series, title: str, critical_threshold: int) -> str:
    fig, ax = plt.subplots(figsize=(7, 3.5))
    n_bins = min(60, max(10, counts.nunique()))
    ax.hist(counts, bins=n_bins, color="#4e79a7", edgecolor="white", linewidth=0.4)
    ax.axvline(critical_threshold, color="#e15759", linestyle="--", linewidth=1.5,
               label=f"Critical threshold ({critical_threshold})")
    ax.set_title(title, fontsize=11, pad=8)
    ax.set_xlabel("Units per study area")
    ax.set_ylabel("Study areas")
    ax.legend(fontsize=9)
    fig.tight_layout()
    return _fig_to_b64(fig)


def _barh_b64(series: pd.Series, title: str, xlabel: str) -> str:
    n = len(series)
    fig, ax = plt.subplots(figsize=(7, max(3.0, n * 0.28 + 1.2)))
    series.plot.barh(ax=ax, color="#76b7b2", edgecolor="white", linewidth=0.4)
    ax.set_title(title, fontsize=11, pad=8)
    ax.set_xlabel(xlabel)
    ax.invert_yaxis()
    fig.tight_layout()
    return _fig_to_b64(fig)


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------

def _esc(v: object) -> str:
    return str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _df_to_html(
    df: pd.DataFrame,
    highlight_col: Optional[str] = None,
    highlight_thresh: Optional[int] = None,
    warn_col: Optional[str] = None,
    warn_thresh: Optional[float] = None,
) -> str:
    if df.empty:
        return "<p class='empty-note'>No data available.</p>"
    rows = []
    for _, row in df.iterrows():
        tds = []
        for col in df.columns:
            val = row[col]
            if (highlight_col == col and highlight_thresh is not None
                    and isinstance(val, (int, float)) and val > 0 and val < highlight_thresh):
                tds.append(f'<td class="critical">{_esc(val)}</td>')
            elif (warn_col == col and warn_thresh is not None
                    and isinstance(val, (int, float)) and val < warn_thresh):
                tds.append(f'<td class="warn">{_esc(val)}</td>')
            else:
                tds.append(f"<td>{_esc(val)}</td>")
        rows.append(f"<tr>{''.join(tds)}</tr>")
    header = "".join(f"<th>{_esc(c)}</th>" for c in df.columns)
    return f'<table><thead><tr>{header}</tr></thead><tbody>{"".join(rows)}</tbody></table>'


def _stat_card(label: str, value: object, warn: bool = False) -> str:
    cls = "stat-card warn" if warn else "stat-card"
    return (f'<div class="{cls}">'
            f'<div class="label">{_esc(label)}</div>'
            f'<div class="value">{_esc(value)}</div>'
            f'</div>')


# ---------------------------------------------------------------------------
# Per-combination section
# ---------------------------------------------------------------------------

def _combo_section(
    df_combo: pd.DataFrame,
    defs: pd.DataFrame,
    geo_type: str,
    sa_type: str,
    critical_threshold: int,
) -> str:
    anchor = f"{geo_type}-in-{sa_type}"
    label  = f"{geo_type.replace('_', ' ')} in {sa_type.replace('_', ' ')}".title()

    if df_combo.empty:
        return (f'<div class="combo-section" id="{anchor}">'
                f'<h2>{label}</h2>'
                f'<p class="empty-note">No clipped geography files found for this combination. '
                f'Run <code>overlaps.py</code> to generate them.</p>'
                f'</div>\n')

    counts      = df_combo["unit_count"]
    total_sa    = len(df_combo)
    total_units = int(counts.sum())
    n_critical  = int((counts < critical_threshold).sum())

    # stat cards
    cards = (
        _stat_card("Study Areas",         f"{total_sa:,}") +
        _stat_card("Total Units",         f"{total_units:,}") +
        _stat_card("Median / Study Area", f"{counts.median():.0f}") +
        _stat_card("Min",                 f"{counts.min():,}") +
        _stat_card("Max",                 f"{counts.max():,}") +
        _stat_card(f"Critical (<{critical_threshold})", n_critical, warn=n_critical > 0)
    )

    # histogram
    hist_img = _hist_b64(counts, f"Units per study area — {label}", critical_threshold)

    # year breakdown
    year_agg = (
        df_combo.groupby("year")["unit_count"]
        .agg(study_areas="count", total_units="sum",
             median="median", min="min", max="max")
        .reset_index()
        .rename(columns={"year": "Year", "study_areas": "Study Areas",
                         "total_units": "Total Units",
                         "median": "Median", "min": "Min", "max": "Max"})
        .sort_values("Year")
    )
    year_html = _df_to_html(year_agg)

    # missing study areas (cross-reference with definitions)
    defs_sa = defs[defs["sa_type"] == sa_type]
    if not defs_sa.empty:
        years_present = sorted(df_combo["year"].unique())
        miss_rows = []
        for year in years_present:
            vintage_mode = df_combo[df_combo["year"] == year]["vintage"].mode()
            vintage = vintage_mode.iloc[0] if not vintage_mode.empty else ""
            defs_v = defs_sa[defs_sa["vintage"] == vintage]
            present_ids = set(df_combo[df_combo["year"] == year]["sa_id"])
            n_defs = len(defs_v)
            n_present = len(present_ids & set(defs_v["sa_id"]))
            n_missing = n_defs - n_present
            pct = f"{100 * n_present / n_defs:.1f}%" if n_defs else "N/A"
            miss_rows.append({
                "Year":              year,
                "Definitions":       n_defs,
                "With Clipped File": n_present,
                "Missing":           n_missing,
                "Coverage":          pct,
            })
        miss_df = pd.DataFrame(miss_rows)
        missing_html = _df_to_html(miss_df, highlight_col="Missing", highlight_thresh=1,
                                   warn_col="Coverage", warn_thresh=90.0)
    else:
        missing_html = "<p class='empty-note'>No study area definition files found for cross-reference.</p>"

    # critically small table
    if n_critical > 0:
        crit_df = (
            df_combo[counts < critical_threshold]
            [["sa_id", "year", "unit_count", "vintage"]]
            .rename(columns={"sa_id": "Study Area ID", "year": "Year",
                             "unit_count": "Unit Count", "vintage": "Vintage"})
            .sort_values(["Unit Count", "Year"])
        )
        crit_html = _df_to_html(crit_df, highlight_col="Unit Count",
                                highlight_thresh=critical_threshold)
    else:
        crit_html = (f"<p class='empty-note'>No study areas below the threshold "
                     f"of {critical_threshold} units.</p>")

    # state breakdown (explode multi-state study areas)
    exploded = df_combo.explode("states").dropna(subset=["states"])
    exploded = exploded[exploded["states"].astype(str).str.strip() != ""]
    if not exploded.empty:
        state_agg = (
            exploded.groupby("states", sort=False)["unit_count"]
            .agg(study_areas="count", total_units="sum")
            .reset_index()
        )
        state_agg["State"] = state_agg["states"].map(
            lambda s: f"{STATEFP_TO_NAME.get(s, 'Unknown')} ({s})")
        state_agg = (
            state_agg[["State", "study_areas", "total_units"]]
            .rename(columns={"study_areas": "Study Areas Touching State",
                             "total_units": "Total Units from State"})
            .sort_values("Total Units from State", ascending=False)
        )
        bar_img = _barh_b64(
            state_agg.set_index("State")["Total Units from State"],
            f"Total units by state — {label}",
            "Total units",
        )
        state_chart = f'<div class="chart-wrap"><img src="data:image/png;base64,{bar_img}"></div>'
        state_table = _df_to_html(state_agg)
    else:
        state_chart = ""
        state_table = "<p class='empty-note'>No STATEFP data available in these files.</p>"

    return f"""
<div class="combo-section" id="{anchor}">
  <h2>{label}</h2>
  <div class="stats-grid">{cards}</div>

  <h3>Distribution of Units per Study Area</h3>
  <div class="chart-wrap">
    <img src="data:image/png;base64,{hist_img}" style="max-width:700px">
  </div>

  <h3>Coverage by Year</h3>
  {year_html}

  <h3>Missing Study Areas vs Definitions</h3>
  {missing_html}

  <h3>Critically Small Study Areas (&lt;{critical_threshold} units)</h3>
  {crit_html}

  <h3>Units by State</h3>
  {state_chart}
  {state_table}
</div>
"""


# ---------------------------------------------------------------------------
# Full report
# ---------------------------------------------------------------------------

def _build_report(
    df: pd.DataFrame,
    defs: pd.DataFrame,
    critical_threshold: int,
    combos: list[tuple[str, str]],
) -> str:
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    # overview table
    ov_rows = []
    for geo, sa in combos:
        sub = df[(df["geo_type"] == geo) & (df["sa_type"] == sa)]
        n_sa       = len(sub)
        n_crit     = int((sub["unit_count"] < critical_threshold).sum()) if not sub.empty else 0
        tot_units  = int(sub["unit_count"].sum()) if not sub.empty else 0
        if n_sa == 0:
            badge = '<span class="badge badge-none">–</span>'
        elif n_crit > 0:
            badge = '<span class="badge badge-warn">⚠ has critical</span>'
        else:
            badge = '<span class="badge badge-ok">✓ ok</span>'
        lbl = f"{geo.replace('_',' ')} in {sa.replace('_',' ')}".title()
        anc = f"{geo}-in-{sa}"
        ov_rows.append(
            f"<tr><td><a href='#{anc}'>{lbl}</a></td>"
            f"<td>{n_sa:,}</td><td>{tot_units:,}</td>"
            f'<td class="{"critical" if n_crit else ""}">{n_crit}</td>'
            f"<td>{badge}</td></tr>"
        )
    overview_tbl = (
        f"<table><thead><tr>"
        f"<th>Combination</th><th>Study Areas Found</th><th>Total Units</th>"
        f"<th>Critical (&lt;{critical_threshold})</th><th>Status</th>"
        f"</tr></thead><tbody>{''.join(ov_rows)}</tbody></table>"
    )

    toc_items = "\n".join(
        f'<li><a href="#{g}-in-{s}">{g.replace("_"," ").title()} in {s.replace("_"," ").title()}</a></li>'
        for g, s in combos
    )

    sections = "\n".join(
        _combo_section(
            df[(df["geo_type"] == g) & (df["sa_type"] == s)].copy(),
            defs, g, s, critical_threshold,
        )
        for g, s in combos
    )

    n_total_files = len(df)
    n_combos_with_data = sum(
        1 for g, s in combos
        if not df[(df["geo_type"] == g) & (df["sa_type"] == s)].empty
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Overlap Quality Report</title>
  <style>{_CSS}</style>
</head>
<body>
<div class="container">
  <h1>Overlap Quality Report</h1>
  <p class="subtitle">
    Generated {now} &nbsp;|&nbsp;
    {n_total_files:,} clipped files across {n_combos_with_data} of {len(combos)} combinations &nbsp;|&nbsp;
    Critical threshold: &lt;{critical_threshold} units
  </p>

  <div class="toc">
    <strong>Contents</strong>
    <ul>
      <li><a href="#overview">Overview</a></li>
      {toc_items}
    </ul>
  </div>

  <h2 id="overview">Overview</h2>
  {overview_tbl}

  {sections}
</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(
    clipped_geographies_dir: str = typer.Argument(
        "data/shared/processed/clipped_geographies",
        help="Directory containing year-based subdirs of clipped gpkg files.",
    ),
    study_area_definitions_dir: str = typer.Option(
        "data/shared/processed/study_area_definitions",
        "--definitions-dir",
        help="Directory containing study area definition gpkg files.",
    ),
    output_path: str = typer.Option(
        "data/shared/outputs/overlap_quality_report.html",
        "--output",
        "-o",
        help="Path for the HTML report.",
    ),
    census_geography_type: str = typer.Option(
        "",
        "--geo-type",
        help="Filter to one geography type (tracts, block_groups, blocks, counties). Empty = all.",
    ),
    study_area_type: str = typer.Option(
        "",
        "--sa-type",
        help="Filter to one study area type (cbsa, county, max_city, max_county). Empty = all.",
    ),
    critical_threshold: int = typer.Option(
        5,
        "--critical-threshold",
        help="Flag study areas with fewer than this many units as critically small.",
    ),
) -> None:
    """Analyze overlap assignment quality and write a self-contained HTML report."""
    clipped_dir = Path(clipped_geographies_dir)
    def_dir     = Path(study_area_definitions_dir)
    out_path    = Path(output_path)

    if not clipped_dir.exists():
        print(f"ERROR: clipped geographies directory not found: {clipped_dir}", file=sys.stderr)
        raise typer.Exit(1)

    print(f"Scanning {clipped_dir} …")
    df = _collect_clipped_records(clipped_dir, census_geography_type, study_area_type)
    print(f"  → {len(df):,} matching files found.")

    defs = _collect_definitions(def_dir) if def_dir.exists() else pd.DataFrame(
        columns=["sa_type", "sa_id", "vintage"])
    print(f"  → {len(defs):,} study area definition files found.")

    # Determine which combos appear in the report
    if census_geography_type or study_area_type:
        combos = [
            (g, s) for g, s in ALL_COMBOS
            if (not census_geography_type or g == census_geography_type)
            and (not study_area_type       or s == study_area_type)
        ]
    else:
        combos = list(ALL_COMBOS)

    print("Building report …")
    html = _build_report(df, defs, critical_threshold, combos)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"Report written → {out_path}")


if __name__ == "__main__":
    typer.run(main)
