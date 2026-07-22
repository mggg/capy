import os
import shutil
import zipfile
from pathlib import Path
from typing import List, Optional

from census import Census
from census.core import CensusException
from ipumspy import AggregateDataExtract, IpumsApiClient, NhgisDataset
import pandas as pd
import typer


OUTPUT_DIR = Path("data/raw/population")
NHGIS_EXTRACTS_DIR = Path("data/raw/population/ipums_population_extracts")
DEFAULT_YEARS = [1980, 1990, 2000, 2010, 2020]

STATES = [
    "01", "02", "04", "05", "06", "08", "09", "10", "11", "12", "13",
    "15", "16", "17", "18", "19", "20", "21", "22", "23", "24", "25",
    "26", "27", "28", "29", "30", "31", "32", "33", "34", "35", "36",
    "37", "38", "39", "40", "41", "42", "44", "45", "46", "47", "48",
    "49", "50", "51", "53", "54", "55", "56", "72",
]

LEVELS = {
    "tract": {
        "label": "tracts",
        "nhgis": "tract",
        "census_for": "tract:*",
        "census_in": "state:{state} county:*",
        "geoid_cols": ("state", "county", "tract"),
    },
    "tracts": {
        "label": "tracts",
        "nhgis": "tract",
        "census_for": "tract:*",
        "census_in": "state:{state} county:*",
        "geoid_cols": ("state", "county", "tract"),
    },
    "block_group": {
        "label": "block_groups",
        "nhgis": "blck_grp",
        "census_for": "block group:*",
        "census_in": "state:{state} county:* tract:*",
        "geoid_cols": ("state", "county", "tract", "block group"),
    },
    "block_groups": {
        "label": "block_groups",
        "nhgis": "blck_grp",
        "census_for": "block group:*",
        "census_in": "state:{state} county:* tract:*",
        "geoid_cols": ("state", "county", "tract", "block group"),
    },
    "block": {
        "label": "blocks",
        "nhgis": "block",
        "census_for": "block:*",
        "census_in": "state:{state} county:* tract:*",
        "geoid_cols": ("state", "county", "tract", "block"),
    },
    "blocks": {
        "label": "blocks",
        "nhgis": "block",
        "census_for": "block:*",
        "census_in": "state:{state} county:* tract:*",
        "geoid_cols": ("state", "county", "tract", "block"),
    },
    "county": {
        "label": "counties",
        "nhgis": "county",
        "census_for": "county:*",
        "census_in": "state:{state}",
        "geoid_cols": ("state", "county"),
    },
    "counties": {
        "label": "counties",
        "nhgis": "county",
        "census_for": "county:*",
        "census_in": "state:{state}",
        "geoid_cols": ("state", "county"),
    },
}

CENSUS_COLUMNS = {
    2000: {
        "PL001001": "TOTPOP",
        "PL001003": "WHITE",
        "PL001004": "BLACK",
        "PL001005": "AMIN",
        "PL001006": "ASIAN",
        "PL001007": "NHPI",
        "PL001008": "OTHER",
        "PL001009": "TWO_OR_MORE",
        "PL002002": "HISPANIC",
        "PL002005": "NH_WHITE",
        "PL002006": "NH_BLACK",
    },
    2010: {
        "P001001": "TOTPOP",
        "P001003": "WHITE",
        "P001004": "BLACK",
        "P001005": "AMIN",
        "P001006": "ASIAN",
        "P001007": "NHPI",
        "P001008": "OTHER",
        "P001009": "TWO_OR_MORE",
        "P002002": "HISPANIC",
        "P002005": "NH_WHITE",
        "P002006": "NH_BLACK",
    },
    2020: {
        "P1_001N": "TOTPOP",
        "P1_003N": "WHITE",
        "P1_004N": "BLACK",
        "P1_005N": "AMIN",
        "P1_006N": "ASIAN",
        "P1_007N": "NHPI",
        "P1_008N": "OTHER",
        "P1_009N": "TWO_OR_MORE",
        "P2_002N": "HISPANIC",
        "P2_005N": "NH_WHITE",
        "P2_006N": "NH_BLACK",
    },
}

CENSUS_SF1_COLUMNS = {
    2000: {
        "P001001": "TOTPOP",
        "P003003": "WHITE",
        "P003004": "BLACK",
        "P003005": "AMIN",
        "P003006": "ASIAN",
        "P003007": "NHPI",
        "P003008": "OTHER",
        "P003009": "TWO_OR_MORE",
        "P004002": "HISPANIC",
        "P004005": "NH_WHITE",
        "P004006": "NH_BLACK",
    },
}

NHGIS_DATASETS = {
    1980: {
        "dataset": "1980_STF1",
        "data_tables": ["NT7", "NT9A", "NT9B"],
        "geog_levels": {
            "counties": ["county"],
            "tracts": ["tract"],
            "block_groups": ["blck_grp_01598"],
            "blocks": ["block_02198", "block_02598"],
        },
        "breakdown_values": {
            "block_groups": ["bs03.ge0100", "bs03.ge0800"],
        },
    },
    1990: {
        "dataset": "1990_STF1",
        "data_tables": ["NP10"],
        "geog_levels": {
            "counties": ["county"],
            "tracts": ["tract"],
            "block_groups": ["blck_grp"],
            "blocks": ["block"],
        },
    },
}


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"{name} is required; set it in the environment or .env.")
    return value


def selected_states(states: Optional[str]) -> List[str]:
    if states is None:
        return STATES
    return [state.strip().zfill(2) for state in states.split(",") if state.strip()]


def parse_years(years: Optional[str], year_values: Optional[List[int]]) -> List[int]:
    if year_values:
        return year_values
    if years:
        return [int(year) for year in years.replace(",", " ").split()]
    return DEFAULT_YEARS


def normalized_geoid_part(df: pd.DataFrame, col: str, width: int, year: int) -> pd.Series:
    text = df[col].astype(str).str.strip()
    if col == "tract" and year == 2000:
        short = text.str.len() < width
        normalized = text.str.zfill(width)
        normalized.loc[short] = text.loc[short].str.zfill(4).str.ljust(width, "0")
        return normalized
    return text.str.zfill(width)


def geoid(df: pd.DataFrame, cols: tuple, year: int) -> pd.Series:
    widths = {
        "state": 2,
        "county": 3,
        "tract": 6,
        "block group": 1,
        "block": 4,
    }
    out = pd.Series([""] * len(df), index=df.index)
    for col in cols:
        out = out + normalized_geoid_part(df, col, widths[col], year)
    return out


def fetch_county_scoped_census_rows(
    table,
    variables: List[str],
    config: dict,
    state: str,
    progress: bool = True,
) -> list:
    counties = table.get(
        ["NAME"],
        geo={"for": "county:*", "in": f"state:{state}"},
    )
    rows = []
    for index, county in enumerate(counties, start=1):
        county_fips = county["county"]
        if progress:
            print(
                f"  state {state} county {county_fips} ({index}/{len(counties)})",
                flush=True,
            )
        rows.extend(
            table.get(
                variables,
                geo={
                    "for": config["census_for"],
                    "in": f"state:{state} county:{county_fips} tract:*",
                },
            )
        )
    return rows


def fetch_census_state_rows(
    table,
    variables: List[str],
    config: dict,
    state: str,
    progress: bool = True,
) -> list:
    if config["label"] == "blocks":
        return fetch_county_scoped_census_rows(
            table, variables, config, state, progress=progress
        )

    geo = {
        "for": config["census_for"],
        "in": config["census_in"].format(state=state),
    }
    if config["label"] == "block_groups":
        try:
            return table.get(variables, geo=geo)
        except CensusException as exc:
            if progress:
                print(
                    "  state-wide block group query failed; "
                    f"falling back to county-by-county: {exc}",
                    flush=True,
                )
            return fetch_county_scoped_census_rows(
                table, variables, config, state, progress=progress
            )

    return table.get(variables, geo=geo)


def fetch_census(year: int, level: str, states: List[str], output_dir: Path) -> Path:
    if year not in CENSUS_COLUMNS:
        raise ValueError(f"{year} is not configured for the Census API path.")

    api_key = require_env("CENSUS_API_KEY")
    census = Census(key=api_key, year=year)
    config = LEVELS[level]

    columns = CENSUS_COLUMNS[year]
    table = census.pl
    if year == 2000 and config["label"] == "block_groups":
        columns = CENSUS_SF1_COLUMNS[year]
        table = census.sf1

    variables = ["NAME"] + list(columns)

    rows = []
    for state in states:
        print(
            f"Fetching {year} {config['label']} population for state {state}",
            flush=True,
        )
        rows.extend(fetch_census_state_rows(table, variables, config, state))

    if not rows:
        raise ValueError(f"Census returned no rows for {year} {config['label']}.")

    df = pd.DataFrame(rows).rename(columns=columns)
    df.insert(0, "YEAR", year)
    df.insert(1, "GEOID", geoid(df, config["geoid_cols"], year))

    population_cols = list(columns.values())
    df[population_cols] = df[population_cols].astype(int)
    df["POC"] = df["TOTPOP"] - df["NH_WHITE"]

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"census_{year}_{config['label']}.csv"
    df.to_csv(output_path, index=False)
    return output_path


def fetch_nhgis(year: int, level: str, output_dir: Path, work_dir: Path) -> Path:
    if year not in NHGIS_DATASETS:
        raise ValueError(f"{year} is not configured for the NHGIS API path.")

    config = LEVELS[level]
    dataset = NHGIS_DATASETS[year]
    geog_levels = dataset["geog_levels"].get(config["label"])
    breakdown_values = dataset.get("breakdown_values", {}).get(config["label"], [])

    if geog_levels is None:
        raise ValueError(
            f"{year} {dataset['dataset']} does not support {config['label']}."
        )

    api_key = require_env("IPUMS_API_KEY")
    client = IpumsApiClient(api_key)

    extract = AggregateDataExtract(
        collection="nhgis",
        description=f"{year} {config['label']} population",
        data_format="csv_header",
        datasets=[
            NhgisDataset(
                name=dataset["dataset"],
                data_tables=dataset["data_tables"],
                geog_levels=geog_levels,
                breakdown_values=breakdown_values,
            )
        ],
    )

    submitted = client.submit_extract(extract)
    print(
        f"Waiting for NHGIS {year} {config['label']} population extract",
        flush=True,
    )
    client.wait_for_extract(submitted, timeout=10800)

    work_dir.mkdir(parents=True, exist_ok=True)
    existing_zips = set(work_dir.glob("*.zip"))
    print(
        f"Downloading NHGIS {year} {config['label']} population extract",
        flush=True,
    )
    client.download_extract(submitted, download_dir=work_dir)

    zip_files = sorted(
        set(work_dir.glob("*.zip")) - existing_zips,
        key=lambda path: path.stat().st_mtime,
    )
    if not zip_files:
        raise FileNotFoundError(f"No new NHGIS zip downloaded to {work_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"nhgis_{year}_{config['label']}.csv"
    with zipfile.ZipFile(zip_files[-1]) as zf:
        csv_names = [name for name in zf.namelist() if name.lower().endswith(".csv")]
        if not csv_names:
            raise ValueError(f"Expected at least one CSV in {zip_files[-1]}")
        if len(csv_names) == 1:
            with zf.open(csv_names[0]) as src, output_path.open("wb") as dst:
                shutil.copyfileobj(src, dst)
        else:
            frames = []
            for name in csv_names:
                frame = pd.read_csv(zf.open(name), dtype=str)
                frame.insert(0, "NHGIS_SOURCE_FILE", name)
                frames.append(frame)
            df = pd.concat(frames, ignore_index=True)
            df.to_csv(output_path, index=False)

    return output_path


def main(
    level: str = typer.Option("tracts", help="tracts, block_groups, blocks, or counties"),
    years: Optional[str] = typer.Option(None, "--years", help="Space- or comma-separated years."),
    year_values: Optional[List[int]] = typer.Option(None, "--year", "-y"),
    states: Optional[str] = typer.Option(None, help="Comma-separated state FIPS codes"),
    output_dir: Path = typer.Option(OUTPUT_DIR),
    work_dir: Path = typer.Option(NHGIS_EXTRACTS_DIR),
    env_file: Path = typer.Option(Path(".env")),
) -> None:
    load_dotenv(env_file)

    if level not in LEVELS:
        raise ValueError(f"Unsupported level {level}. Use one of: {sorted(LEVELS)}")

    run_years = parse_years(years, year_values)
    state_fips = selected_states(states)

    config = LEVELS[level]
    for year in run_years:
        if year in NHGIS_DATASETS:
            output_path = output_dir / f"nhgis_{year}_{config['label']}.csv"
            if output_path.exists():
                print(f"Skipping existing {output_path}", flush=True)
                print(output_path)
                continue
            path = fetch_nhgis(year, level, output_dir, work_dir / str(year))
        elif year in CENSUS_COLUMNS:
            output_path = output_dir / f"census_{year}_{config['label']}.csv"
            if output_path.exists():
                print(f"Skipping existing {output_path}", flush=True)
                print(output_path)
                continue
            path = fetch_census(year, level, state_fips, output_dir)
        else:
            raise ValueError(f"No source is configured for {year}")
        print(path)


if __name__ == "__main__":
    typer.run(main)
