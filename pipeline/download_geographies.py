import os
import re
import urllib.request
import zipfile
from pathlib import Path
from typing import List, Optional

from ipumspy import AggregateDataExtract, IpumsApiClient, Shapefile
import typer


OUTPUT_DIR = Path("census_raw/geographies")

STATE_FIPS = [
    "01", "02", "04", "05", "06", "08", "09", "10", "11", "12", "13",
    "15", "16", "17", "18", "19", "20", "21", "22", "23", "24", "25",
    "26", "27", "28", "29", "30", "31", "32", "33", "34", "35", "36",
    "37", "38", "39", "40", "41", "42", "44", "45", "46", "47", "48",
    "49", "50", "51", "53", "54", "55", "56",
    "60", "66", "69", "72", "78",
]

LEVELS = {
    "county": {"label": "counties", "nhgis_levels": ["county"], "census": "county"},
    "counties": {"label": "counties", "nhgis_levels": ["county"], "census": "county"},
    "tract": {
        "label": "tracts",
        "nhgis_levels": ["census tract", "tract"],
        "census": "tract",
    },
    "tracts": {
        "label": "tracts",
        "nhgis_levels": ["census tract", "tract"],
        "census": "tract",
    },
    "block_group": {
        "label": "block_groups",
        "nhgis_levels": ["block group"],
        "census": "block_group",
    },
    "block_groups": {
        "label": "block_groups",
        "nhgis_levels": ["block group"],
        "census": "block_group",
    },
    "block": {"label": "blocks", "nhgis_levels": ["block"], "census": "block"},
    "blocks": {"label": "blocks", "nhgis_levels": ["block"], "census": "block"},
}

CENSUS_TIGER_URLS = {
    2000: {
        "county": [
            "https://www2.census.gov/geo/tiger/TIGER2010/COUNTY/2000/"
            "tl_2010_us_county00.zip"
        ],
        "tract": [
            "https://www2.census.gov/geo/tiger/TIGER2010/TRACT/2000/"
            "tl_2010_{state}_tract00.zip"
        ],
        "block_group": [
            "https://www2.census.gov/geo/tiger/TIGER2010/BG/2000/"
            "tl_2010_{state}_bg00.zip"
        ],
        "block": [
            "https://www2.census.gov/geo/tiger/TIGER2010/TABBLOCK/2000/"
            "tl_2010_{state}_tabblock00.zip"
        ],
    },
    2010: {
        "county": [
            "https://www2.census.gov/geo/tiger/TIGER2010/COUNTY/2010/"
            "tl_2010_us_county10.zip"
        ],
        "tract": [
            "https://www2.census.gov/geo/tiger/TIGER2010/TRACT/2010/"
            "tl_2010_{state}_tract10.zip"
        ],
        "block_group": [
            "https://www2.census.gov/geo/tiger/TIGER2010/BG/2010/"
            "tl_2010_{state}_bg10.zip"
        ],
        "block": [
            "https://www2.census.gov/geo/tiger/TIGER2010/TABBLOCK/2010/"
            "tl_2010_{state}_tabblock10.zip"
        ],
    },
    2020: {
        "county": [
            "https://www2.census.gov/geo/tiger/TIGER2020/COUNTY/"
            "tl_2020_us_county.zip"
        ],
        "tract": [
            "https://www2.census.gov/geo/tiger/TIGER2020/TRACT/"
            "tl_2020_{state}_tract.zip"
        ],
        "block_group": [
            "https://www2.census.gov/geo/tiger/TIGER2020/BG/"
            "tl_2020_{state}_bg.zip"
        ],
        "block": [
            "https://www2.census.gov/geo/tiger/TIGER2020/TABBLOCK20/"
            "tl_2020_{state}_tabblock20.zip"
        ],
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


def download(url: str, zip_path: Path) -> Path:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if not zip_path.exists():
        print(f"Downloading {url}")
        urllib.request.urlretrieve(url, zip_path)
    return zip_path


def extract_zip(zip_path: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(output_dir)


def clean_text(value: str) -> str:
    return " ".join(value.lower().replace("_", " ").split())


def basis_year(shapefile: dict) -> int:
    text = f"{shapefile.get('name', '')} {shapefile.get('basis', '')}"
    years = [int(year) for year in re.findall(r"(?:18|19|20)\d{2}", text)]
    return max(years) if years else 0


def nhgis_shapefiles(
    client: IpumsApiClient,
    year: int,
    level: str,
) -> List[str]:
    config = LEVELS[level]
    wanted_levels = {clean_text(value) for value in config["nhgis_levels"]}

    matches = []
    for page in client.get_metadata_catalog("nhgis", "shapefiles"):
        for shapefile in page["data"]:
            shapefile_year = str(shapefile.get("year"))
            shapefile_level = clean_text(shapefile.get("geographicLevel", ""))
            if shapefile_year != str(year):
                continue
            if shapefile_level not in wanted_levels:
                continue
            matches.append(shapefile)

    if not matches:
        raise ValueError(f"NHGIS returned no shapefiles for {year} {config['label']}.")

    national_matches = [
        shapefile
        for shapefile in matches
        if clean_text(shapefile.get("extent", "")) == "united states"
    ]
    if national_matches:
        matches = national_matches

    # NHGIS can list alternate bases for the same extent; keep the newest.
    selected = {}
    for shapefile in sorted(
        matches,
        key=lambda item: (basis_year(item), int(item["sequence"])),
    ):
        selected[shapefile["extent"]] = shapefile

    names = [shapefile["name"] for shapefile in selected.values()]
    print("NHGIS shapefiles:", ", ".join(names))
    return names


def fetch_nhgis(
    year: int,
    level: str,
    work_dir: Path,
) -> Path:
    api_key = os.environ["IPUMS_API_KEY"]
    client = IpumsApiClient(api_key)
    config = LEVELS[level]
    shapefiles = nhgis_shapefiles(client, year, level)

    extract = AggregateDataExtract(
        collection="nhgis",
        description=f"{year} {config['label']} shapefiles",
        shapefiles=[Shapefile(name) for name in shapefiles],
    )

    submitted = client.submit_extract(extract)
    client.wait_for_extract(submitted, timeout=10800)

    work_dir.mkdir(parents=True, exist_ok=True)
    existing_zips = set(work_dir.glob("*.zip"))
    client.download_extract(submitted, download_dir=work_dir)

    zip_files = sorted(
        set(work_dir.glob("*.zip")) - existing_zips,
        key=lambda path: path.stat().st_mtime,
    )
    if not zip_files:
        raise FileNotFoundError(f"No new NHGIS zip downloaded to {work_dir}")

    return zip_files[-1]


def fetch_census(year: int, level: str, output_dir: Path) -> Path:
    if year not in CENSUS_TIGER_URLS:
        raise ValueError(f"{year} is not configured for Census TIGER downloads.")

    config = LEVELS[level]
    templates = CENSUS_TIGER_URLS[year][config["census"]]
    output_path = output_dir / f"census_{year}_{config['label']}"
    zip_dir = output_path / "zips"

    for template in templates:
        urls = [template]
        if "{state}" in template:
            urls = [template.format(state=state) for state in STATE_FIPS]

        for url in urls:
            zip_path = download(url, zip_dir / url.split("/")[-1])
            extract_zip(zip_path, output_path)

    return output_path


def main(
    level: str = typer.Option(
        "tracts",
        help="tracts, block_groups, blocks, or counties",
    ),
    years: Optional[List[int]] = typer.Option(None, "--year", "-y"),
    output_dir: Path = typer.Option(OUTPUT_DIR),
    work_dir: Path = typer.Option(Path("census_raw/geographies/ipums_geography_extracts")),
    env_file: Path = typer.Option(Path(".env")),
) -> None:
    load_dotenv(env_file)

    if level not in LEVELS:
        raise ValueError(f"Unsupported level {level}. Use one of: {sorted(LEVELS)}")

    run_years = years or [1980, 1990, 2000, 2010, 2020]

    for year in run_years:
        if year in (1980, 1990):
            path = fetch_nhgis(
                year,
                level,
                work_dir / str(year),
            )
        elif year in CENSUS_TIGER_URLS:
            path = fetch_census(year, level, output_dir)
        else:
            raise ValueError(f"No geography source is configured for {year}")
        print(path)


if __name__ == "__main__":
    typer.run(main)
