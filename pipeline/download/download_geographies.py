import os
import re
import time
import zipfile
from pathlib import Path
from typing import List, Optional

from ipumspy import AggregateDataExtract, IpumsApiClient, Shapefile
import requests
import typer


OUTPUT_DIR = Path("data/raw/geographies")
DEFAULT_YEARS = [1980, 1990, 2000, 2010, 2020]
DOWNLOAD_CHUNK_SIZE = 1024 * 1024
DOWNLOAD_TIMEOUT = (20, 180)
DOWNLOAD_HEADERS = {
    "Accept": "application/zip,*/*",
    "Accept-Encoding": "identity",
    "Connection": "close",
    "User-Agent": "capy-bara geography downloader",
}

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
        "nhgis_levels": ["census tract", "tract", "block numbering area", "bna"],
        "nhgis_name_fragments": ["tract", "bna"],
        "census": "tract",
    },
    "tracts": {
        "label": "tracts",
        "nhgis_levels": ["census tract", "tract", "block numbering area", "bna"],
        "nhgis_name_fragments": ["tract", "bna"],
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


def parse_years(years: Optional[str], year_values: Optional[List[int]]) -> List[int]:
    if year_values:
        return year_values
    if years:
        return [int(year) for year in years.replace(",", " ").split()]
    return DEFAULT_YEARS


def zip_is_readable(zip_path: Path) -> bool:
    if not zip_path.exists():
        return False
    try:
        with zipfile.ZipFile(zip_path) as zf:
            return zf.testzip() is None
    except zipfile.BadZipFile:
        return False


class IncompleteDownloadError(RuntimeError):
    pass


def download_to_file(url: str, destination: Path) -> int:
    bytes_written = 0
    with requests.get(
        url,
        stream=True,
        timeout=DOWNLOAD_TIMEOUT,
        headers=DOWNLOAD_HEADERS,
    ) as response:
        response.raise_for_status()
        expected_size = response.headers.get("Content-Length")
        with destination.open("wb") as dst:
            for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                if not chunk:
                    continue
                dst.write(chunk)
                bytes_written += len(chunk)

    if expected_size is not None and bytes_written != int(expected_size):
        raise IncompleteDownloadError(
            f"retrieval incomplete: got {bytes_written} out of "
            f"{expected_size} bytes"
        )

    return bytes_written


def download(url: str, zip_path: Path, attempts: int = 5) -> Path:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        print(f"Replacing existing zip {zip_path}", flush=True)
        zip_path.unlink()

    partial_path = zip_path.with_name(f"{zip_path.name}.part")
    for attempt in range(1, attempts + 1):
        if partial_path.exists():
            partial_path.unlink()
        try:
            print(f"Downloading {url} (attempt {attempt}/{attempts})", flush=True)
            bytes_written = download_to_file(url, partial_path)
            if not zip_is_readable(partial_path):
                raise zipfile.BadZipFile(f"{partial_path} is not a readable zip")
            print(f"Downloaded {bytes_written} bytes to {zip_path}", flush=True)
            partial_path.replace(zip_path)
            return zip_path
        except (
            OSError,
            requests.RequestException,
            IncompleteDownloadError,
            zipfile.BadZipFile,
        ) as exc:
            if partial_path.exists():
                partial_path.unlink()
            if attempt == attempts:
                raise RuntimeError(
                    f"Failed to download a readable zip from {url} after "
                    f"{attempts} attempts"
                ) from exc
            time.sleep(min(2 ** attempt, 10))

    raise RuntimeError(f"Failed to download {url}")


def extract_zip(zip_path: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(output_dir)


def census_output_exists(url: str, output_dir: Path) -> bool:
    stem = Path(url).stem
    return (output_dir / f"{stem}.shp").exists()


def existing_nhgis_zip(work_dir: Path) -> Optional[Path]:
    zip_files = sorted(work_dir.glob("*.zip"), key=lambda path: path.stat().st_mtime)
    if zip_files:
        return zip_files[-1]
    return None


def clean_text(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).split())


def basis_year(shapefile: dict) -> int:
    text = f"{shapefile.get('name', '')} {shapefile.get('basis', '')}"
    years = [int(year) for year in re.findall(r"(?:18|19|20)\d{2}", text)]
    return max(years) if years else 0


def is_conflated(shapefile: dict) -> bool:
    text = clean_text(f"{shapefile.get('name', '')} {shapefile.get('basis', '')}")
    return "conflated" in text or "tl2008" in text or "2008 tiger line" in text


def is_county_sidecar(shapefile: dict) -> bool:
    text = clean_text(
        f"{shapefile.get('name', '')} {shapefile.get('geographicLevel', '')}"
    )
    compact = text.replace(" ", "")
    return (
        "tractcounty" in compact
        or "countytract" in compact
        or "tract county" in text
        or "county tract" in text
    )


def shapefile_key(shapefile: dict) -> tuple:
    return (
        clean_text(shapefile.get("extent", "")),
        clean_text(shapefile.get("geographicLevel", "")),
    )


def matches_level(shapefile: dict, config: dict) -> bool:
    if config["label"] == "tracts" and is_county_sidecar(shapefile):
        return False

    shapefile_level = clean_text(shapefile.get("geographicLevel", ""))
    if shapefile_level in {clean_text(value) for value in config["nhgis_levels"]}:
        return True

    name = clean_text(shapefile.get("name", ""))
    return any(
        clean_text(fragment) in name
        for fragment in config.get("nhgis_name_fragments", [])
    )


def select_shapefile_names(matches: List[dict], year: int, level: str) -> List[str]:
    config = LEVELS[level]

    if config["label"] == "tracts":
        matches = [
            shapefile for shapefile in matches if not is_county_sidecar(shapefile)
        ]

    national_matches = [
        shapefile
        for shapefile in matches
        if clean_text(shapefile.get("extent", "")) == "united states"
    ]
    if national_matches:
        matches = national_matches

    if config["label"] == "tracts" and year in (1980, 1990):
        non_conflated = [
            shapefile for shapefile in matches if not is_conflated(shapefile)
        ]
        if not non_conflated:
            candidates = ", ".join(
                f"{item.get('name')} ({item.get('geographicLevel')}, {item.get('basis')})"
                for item in matches
            )
            raise ValueError(
                f"NHGIS returned only conflated tract shapefiles for {year}. "
                "Expected original tract/BNA files. "
                f"Candidates: {candidates}"
            )
        matches = non_conflated

    # NHGIS can list alternate bases for the same extent and level. Keep one
    # per extent/level so tract and BNA files are both preserved.
    selected = {}
    for shapefile in sorted(
        matches,
        key=lambda item: (basis_year(item), int(item.get("sequence") or 0)),
    ):
        selected[shapefile_key(shapefile)] = shapefile

    return [shapefile["name"] for shapefile in selected.values()]


def nhgis_shapefiles(
    client: IpumsApiClient,
    year: int,
    level: str,
) -> List[str]:
    config = LEVELS[level]

    matches = []
    for page in client.get_metadata_catalog("nhgis", "shapefiles"):
        for shapefile in page["data"]:
            shapefile_year = str(shapefile.get("year"))
            if shapefile_year != str(year):
                continue
            if not matches_level(shapefile, config):
                continue
            matches.append(shapefile)

    if not matches:
        raise ValueError(f"NHGIS returned no shapefiles for {year} {config['label']}.")

    names = select_shapefile_names(matches, year, level)
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
            if census_output_exists(url, output_path):
                print(f"Skipping existing geography for {url}", flush=True)
                continue
            zip_path = download(url, zip_dir / url.split("/")[-1])
            extract_zip(zip_path, output_path)

    return output_path


def main(
    level: str = typer.Option(
        "tracts",
        help="tracts, block_groups, blocks, or counties",
    ),
    years: Optional[str] = typer.Option(None, "--years", help="Space- or comma-separated years."),
    year_values: Optional[List[int]] = typer.Option(None, "--year", "-y"),
    output_dir: Path = typer.Option(OUTPUT_DIR),
    work_dir: Path = typer.Option(Path("data/raw/geographies/ipums_geography_extracts")),
    env_file: Path = typer.Option(Path(".env")),
) -> None:
    load_dotenv(env_file)

    if level not in LEVELS:
        raise ValueError(f"Unsupported level {level}. Use one of: {sorted(LEVELS)}")

    level_label = LEVELS[level]["label"]
    run_years = parse_years(years, year_values)

    for year in run_years:
        if year == 1980 and LEVELS[level]["label"] == "block_groups":
            print(
                f"Skipping 1980 {level_label}: NHGIS does not publish 1980 block group "
                "boundary shapefiles. Block groups were not standardized as a nationwide "
                "geographic unit until 1990.",
                flush=True,
            )
            continue
        if year in (1980, 1990):
            year_work_dir = work_dir / str(year) / level_label
            path = existing_nhgis_zip(year_work_dir)
            if path is None:
                path = fetch_nhgis(
                    year,
                    level,
                    year_work_dir,
                )
            else:
                print(f"Skipping existing NHGIS geography extract {path}", flush=True)
        elif year in CENSUS_TIGER_URLS:
            path = fetch_census(year, level, output_dir)
        else:
            raise ValueError(f"No geography source is configured for {year}")
        print(path)


if __name__ == "__main__":
    typer.run(main)
