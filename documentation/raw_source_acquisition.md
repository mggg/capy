# Raw-data retrieval

This guide explains how to choose the pipeline's inputs, where they come from, and how retrieval
checks them before saving. Each input's origin and local filename are recorded in the Python
definitions under [`code/capy_core/retrieve_data/`](../code/capy_core/retrieve_data/), while the
raw files themselves are ignored by Git. For commands to run retrieval, see the
[run guide](../code/README.md).

## Contents

- [Choosing the data](#choosing-the-data)
- [Configuring paths](#configuring-paths)
- [Editing raw inputs](#editing-raw-inputs)
  - [Local names and source filenames](#local-names-and-source-filenames)
- [API documentation and request addresses](#api-documentation-and-request-addresses)
- [Census population variable guide](#census-population-variable-guide)
- [NHGIS request comparisons](#nhgis-request-comparisons)
- [NHGIS table layout](#nhgis-table-layout)
- [NHGIS 1980 geographic subareas](#nhgis-1980-geographic-subareas)
- [Following the code](#following-the-code)
- [Basic checks](#basic-checks)
- [Sources and coverage](#sources-and-coverage)
- [Reusing local files](#reusing-local-files)
- [Published raw checksums](#published-raw-checksums)

## Choosing the data

Choose the Census years and geographic units for a run with `census_geography_years` and
`census_geography_levels`, using the commented [`example.yaml`](../code/configs/example.yaml) for
settings and examples. These selections apply to both population tables and boundaries, whether
supplied by Census or NHGIS. To define the study areas, `study_area_type` and `study_area_vintage`
add the necessary population and boundary inputs: counties for every mode, and 2020 places for
`max_city`. Here, _vintage_ means the year of the geography used to define those areas, which can
differ from the population year.

For example, 1990 tracts with `max_city` and vintage 2020 require 1990 tract data plus 2020 county
and place data. Unsupported 1980 block and block-group combinations are left out. If no supported
year and geography combination remains, the run stops before downloading any files.

Metro study areas always use the March 2020 county-membership workbook, even when the boundary
vintage changes. The retrieval configuration therefore offers no setting to substitute a different
membership list.

NHGIS delivers requested data as an _extract_, a ZIP archive containing the selected files. The
pipeline groups population and boundary archives by year and geography level, for example
`nhgis/1990/tracts/population.zip` and `nhgis/1990/tracts/boundaries.zip`. Each population archive
contains CSV tables for just that level, along with codebooks describing their columns and
geographic coverage. Because completed files and pending submissions are reused independently,
adding blocks to a run does not repeat the tract request.

Supporting inputs follow their actual use:

- State population totals accompany each required year for population checks.
- Historical reference workbooks are requested only for the required historical years.
- Runs that need 2000, 2010, or 2020 data also request the Census 2020 apportionment release,
  which includes historical state population totals for comparison.
- Five original TIGER 1992 county archives supply the missing 1980 BNA outlines for tract runs.
- For 1990 block runs, original STF1B disc archives and California/Connecticut PL tables establish
  empty land blocks. These remain ZIP and DBF files in their published formats.
- County and place files, along with metro membership, follow the selected study-area definition.

Some sources bundle more data than a run needs. Original STF1B disc archives contain several
states and geographic levels, national county shapefiles include their full geographic coverage,
and reference files retain their published contents. The pipeline downloads these files as
supplied rather than rewriting them to remove unused rows.

If you have already downloaded the data, you can
[place the files in their configured folders](#reusing-local-files) so the pipeline can reuse
them. For NHGIS population data, each ZIP file should contain tables for the requested kind of
geographic unit. For example, a request for tracts expects a ZIP containing tract tables only. If
an older download combines tract and block tables, changing its filename does not separate those
tables; download the tract-only selection from NHGIS instead.

For partial downloads, `file_path_patterns` narrows the resulting list by filename, reporting an
error if a pattern matches nothing. Since this filter can exclude study-area data or one side of a
population/boundary pair, leave it as `["*"]` to retrieve all configured inputs. The checksum
command uses the same selection, although it does not add download-only county prerequisites for
2010 blocks.

## Configuring paths

`code/configs/` contains YAML files that configure complete runs. Choose the raw-data directory
and its subdirectories here so request construction and downloading use the same paths. For
example:

```yaml
census_geography_levels: [blocks]
census_geography_years: [2010]
study_area_type: county
study_area_vintage: 2020
raw_data_directory: data/raw
raw_data_subdirectories:
  census_population_tables: tables/census
  nhgis_population_and_boundaries: historical/nhgis
  census_boundary_files: boundaries/tiger
  original_1980_boundary_files: boundaries/tiger_1992
  original_1990_block_references: references/1990_blocks
  population_reference_tables: references/populations
  metro_membership_tables: references/metros
  saved_nhgis_requests: saved_nhgis_requests
env_file: null
offline: false
raw_checksums_file: data/raw_checksums.sha256
file_path_patterns: ["tables/census/2010/blocks/10/*"]
max_parallel_downloads: 4
...
```

Top-level relative paths start at the repository root, while entries under
`raw_data_subdirectories` start at `raw_data_directory`. Those subdirectories must stay inside the
raw-data directory, so absolute paths and `..` are rejected. Within them, generated filenames and
the year/geography/state hierarchy remain fixed: the example saves the Delaware block response as
`data/raw/tables/census/2010/blocks/10/state.json`, with its county prerequisite in the same
configured Census folder. Filename selection patterns must follow this layout, though changing the
settings does not move existing raw files or saved NHGIS submission records.

Settings omitted from the YAML use the defaults in
[`pipeline_config.py`](../code/capy_core/pipeline_config.py). You can enable offline mode with
`--offline` even when the YAML setting is false. For the checksum command, `--output` overrides
`raw_checksums_file`, with a relative path starting at the directory where you run the command.

Use each raw-data directory for one retrieval run at a time, with parallel workers writing to
separate file destinations within that run. Independent runs sharing a directory are not
supported.

## Editing raw inputs

Change the Python request definitions when you need different tables, variables, or source
products. Use the YAML configuration to select among the supported years and geography levels.

In Python, `GeographyLevel` and `StudyAreaType` are enums, or named choices with fixed values,
defined in [`geography_types.py`](../code/capy_core/geography_types.py). For example, Python uses
`GeographyLevel.BLOCK_GROUP`, while YAML uses its string value, `block_groups`. Retrieval then
translates these choices into provider names: blocks use `block` in Census population queries and
`tabblock` or `tabblock20` in TIGER product names. The same distinction applies to study-area
choices such as `max_city`. States and places supply supporting data but are not available as the
units represented by graph nodes.

For Census datasets, `CensusFileRequest` uses `CensusDataset.PL_94_171` or
`CensusDataset.SUMMARY_FILE_1`, defined beside the request record with the API values `pl` and
`sf1`. The same module defines `RawFileFormat`, which identifies the expected contents so
retrieval can choose the appropriate basic checks. Since these checks do not convert files, inputs
retain their original formats until a processing stage modifies them and saves derived outputs
separately.

Request-building functions use the configured subdirectories and create dataclasses, which are
records with named fields. For example, this record describes a published file without downloading
it:

```python
PublicFileRequest(
    destination_relative_path=(
        f"{directories.population_reference_tables}/"
        "census_working_paper_56_1990_tableE-01.xlsx"
    ),
    file_format=RawFileFormat.EXCEL_XLSX,
    url="https://www2.census.gov/library/working-papers/2002/demo/pop-twps0056/tableE-01.xlsx",
)
```

### Local names and source filenames

Local filenames identify the source publication and relevant year when the provider's filename
alone is ambiguous. A different local name does not change the download URL, file format, or
contents. The metro workbook uses `list1_march_2020.xls` to identify the date of its
county-membership list.

| Provider filename   | Local filename                                    | Contents                                                                            |
| ------------------- | ------------------------------------------------- | ----------------------------------------------------------------------------------- |
| `list1_2020.xls`    | `list1_march_2020.xls`                            | March 2020 metropolitan and micropolitan county memberships.                        |
| `apportionment.csv` | `census_state_population_totals_2020_release.csv` | Census 2020 apportionment release, including historical resident population totals. |
| `tableA-03.xlsx`    | `census_working_paper_56_1980_tableA-03.xlsx`     | 1980 detailed race and Hispanic-origin totals.                                      |
| `tableE-01.xlsx`    | `census_working_paper_56_1990_tableE-01.xlsx`     | 1990 race counts separated by Hispanic origin.                                      |
| `tableE-03.xlsx`    | `census_working_paper_56_1980_tableE-03.xlsx`     | 1980 race counts separated by Hispanic origin.                                      |

The three Excel reference tables come from Census
[Population Division Working Paper 56][working-paper-56], published in 2002. The years in their
local names identify the populations described, not the publication year; all three use
100-percent census counts. Their table numbers retain the direct connection to the source
publication. The builders keep the original URLs beside these local names.

TIGER archives and original 1990 block references retain their provider filenames in their
source-specific folders. Selection patterns use the configured local destinations. If you rename a
request, move the existing file to its new location to reuse it; changing the request does not
move the file for you.

Edit the appropriate retrieval definition module:

- [`census/build_requests.py`](../code/capy_core/retrieve_data/census/build_requests.py): the
  complete Census input selection, PL/SF1 variables, and table filename rules. The 2010 block
  queries use county codes read from the retrieved 2010 county tables.
- [`census/build_published_file_requests.py`][published-requests]: Census TIGER files, original
  1990 block references, population reference tables, and metro membership.
- [`nhgis/build_requests.py`](../code/capy_core/retrieve_data/nhgis/build_requests.py): named
  population and boundary extracts.

[`prepare_file_requests.py`](../code/capy_core/retrieve_data/prepare_file_requests.py) contains
`build_raw_file_requests(config)` and `select_raw_file_requests()`. The first builds the run's
input list in destination-path order; the second applies the configured filename patterns. Neither
reads files nor contacts APIs. Shared state FIPS codes are defined in
[`state_codes.py`](../code/capy_core/retrieve_data/state_codes.py), with their coverage documented
beside the list. Records in
[`raw_file_requests.py`](../code/capy_core/retrieve_data/raw_file_requests.py) describe Census
years, datasets, variables, and geographies; NHGIS table or boundary selections; or public URLs.
Census and NHGIS retrieval translate these records into each API's field names.

## API documentation and request addresses

| Service                  | Official documentation                                                                                                                                                               | Where this repository makes requests                                                                      |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------- |
| Census population tables | [API user guide](https://www.census.gov/data/developers/guidance/api-user-guide.html) and [2010 PL geographic query examples](https://api.census.gov/data/2010/dec/pl/examples.html) | [`census/retrieve_tables.py`](../code/capy_core/retrieve_data/census/retrieve_tables.py)                  |
| NHGIS extracts           | [NHGIS API guide](https://developer.ipums.org/docs/v2/apiprogram/apis/nhgis/)                                                                                                        | [`nhgis/retrieve_extract.py`](../code/capy_core/retrieve_data/nhgis/retrieve_extract.py), using `ipumspy` |

The Census table address is constructed once, in `download_census_table()`:
`https://api.census.gov/data/{census_year}/dec/{dataset}`. The dataset is `pl` or `sf1`.
`resolve_census_query_parameters()` builds the column selection (`get`) and geographic selection
(`for` and `in`) separately; the HTTP library adds those parameters to the address. For another
supported dataset/year combination, its `variables.html` and `examples.html` pages are beneath
that same dataset address.

For NHGIS, `IpumsApiClient` handles the API endpoint addresses. Completed extracts provide their
own download links, which can be temporary; they are read from the response rather than fixed in
the code. The table and boundary choices are described separately in the request definitions.

TIGER archives, original 1990 block references, and workbooks use direct file-download URLs rather
than population API queries. Their addresses stay beside their source definitions in
[`census/build_published_file_requests.py`][published-requests], where the file's year, contents,
and destination can be read together.

## Census population variable guide

Edit Census column definitions in
[`census/table_columns.py`](../code/capy_core/retrieve_data/census/table_columns.py). It names the
population columns for each year and dataset, along with the geographic fields. Retrieval and
processing share these definitions so a requested count keeps the same meaning when processed.

The strings in `POPULATION_VARIABLES_BY_YEAR` and `BLOCK_GROUP_VARIABLES_2000` are Census API
column identifiers. They select the columns to download, not filters on which residents to
include. For example, `get=NAME,P1_001N,P2_005N,P2_006N` requests an area's name, total
population, non-Hispanic White population, and non-Hispanic Black population from the 2020 PL
dataset. The `for` and `in` query parameters select geographic units, such as tracts within a
state. The response also includes the geographic code columns needed to identify each row.

PL 94-171 is the Census redistricting data product; SF1 is Summary File 1. This pipeline selects
SF1 for 2000 block groups and PL for its other modern population inputs. Codes must be interpreted
within their year and dataset. The PL race tables are `PL001` in 2000, `P001` in 2010, and `P1` in
2020; the corresponding Hispanic-origin-by-race tables are `PL002`, `P002`, and `P2`. For example,
`P1_003N` identifies the third count in the 2020 P1 table. In 2000 SF1, the selected total comes
from P001, race counts from P003, and Hispanic-origin-by-race counts from P004. See the Census
dictionaries for [2000 PL](https://api.census.gov/data/2000/dec/pl/variables.html),
[2010 PL](https://api.census.gov/data/2010/dec/pl/variables.html),
[2020 PL](https://api.census.gov/data/2020/dec/pl/variables.html), and
[2000 SF1](https://api.census.gov/data/2000/dec/sf1/variables.html).

The table below maps every requested column, with population counts covering all ages. “Alone”
means a person is counted in one race category, while people reporting multiple races appear in
the separate two-or-more-races category. Unless explicitly marked non-Hispanic, the race rows
include both Hispanic and non-Hispanic residents.

| Meaning                                          | 2000 PL    | 2010 PL   | 2020 PL   | 2000 SF1 block groups |
| ------------------------------------------------ | ---------- | --------- | --------- | --------------------- |
| Area's display name, not its unique identifier   | `NAME`     | `NAME`    | `NAME`    | `NAME`                |
| Total population                                 | `PL001001` | `P001001` | `P1_001N` | `P001001`             |
| White alone                                      | `PL001003` | `P001003` | `P1_003N` | `P003003`             |
| Black or African American alone                  | `PL001004` | `P001004` | `P1_004N` | `P003004`             |
| American Indian and Alaska Native alone          | `PL001005` | `P001005` | `P1_005N` | `P003005`             |
| Asian alone                                      | `PL001006` | `P001006` | `P1_006N` | `P003006`             |
| Native Hawaiian and Other Pacific Islander alone | `PL001007` | `P001007` | `P1_007N` | `P003007`             |
| Some other race alone                            | `PL001008` | `P001008` | `P1_008N` | `P003008`             |
| Two or more races                                | `PL001009` | `P001009` | `P1_009N` | `P003009`             |
| Hispanic or Latino, of any race                  | `PL002002` | `P002002` | `P2_002N` | `P004002`             |
| Non-Hispanic White alone                         | `PL002005` | `P002005` | `P2_005N` | `P004005`             |
| Non-Hispanic Black or African American alone     | `PL002006` | `P002006` | `P2_006N` | `P004006`             |

Population processing derives `TOTPOP` from the total row, `WHITE` and `BLACK` from the two
non-Hispanic rows, and `POC = TOTPOP - WHITE`. Census supplies the non-Hispanic counts directly,
so no Hispanic subtraction is needed to obtain them. POC includes Hispanic residents of any race
and everyone else outside the non-Hispanic White-alone category. It is not synonymous with Black
population.

The six single-race counts plus the two-or-more-races count partition the total population. Those
columns support checks of population totals; the Hispanic and non-Hispanic columns describe
overlapping subsets and must not be added to that race sum. Retrieval saves these columns
unchanged. The [population-processing stage](population_processing.md) derives the study fields
and performs these checks for modern Census tables.

## NHGIS request comparisons

Before downloading an extract, retrieval compares NHGIS's description of the prepared data with
the requested selections. Since NHGIS can reorder lists, explicitly report defaults, or omit a
layout setting that has no effect, requiring identical descriptions would reject usable extracts.
The comparison allows these specific cases while still checking that the selections match:

| Requested                                      | Reported by NHGIS             | Why this matches                               |
| ---------------------------------------------- | ----------------------------- | ---------------------------------------------- |
| Tables `NT1A`, `NT7`                           | Tables `NT7`, `NT1A`          | The same tables are selected.                  |
| `1980_STF1`, year omitted                      | Year `1980`                   | This is the dataset's known Census year.       |
| Whole-area breakdown omitted                   | Explicit total-area breakdown | This is the known default for 1980/1990 STF1.  |
| `single_file`, one breakdown and one data type | Layout omitted                | There is nothing to split into separate files. |

Year and breakdown defaults are applied only for `1980_STF1` and `1990_STF1`, using their Census
years and total-area codes (`bs03.ge0000` and `bs09.ge00`, respectively). They are filled in only
for comparison; the saved request is unchanged. The layout allowance is likewise limited to these
datasets and is explained [below](#nhgis-table-layout). Missing tables, changed geographic levels,
and different years or breakdowns still cause retrieval to fail.

Retrieval does not select or compare the version number in NHGIS's response, so this check cannot
establish whether different versions contain equivalent data. It also ignores time-series layout
because this workflow requests no time-series tables. Requested data format and layout settings
must match, except for the omitted-layout case described above.

The comparison verifies NHGIS's description of the prepared extract. Retrieval also performs
[basic file checks](#basic-checks), but population values and geographic matches must be validated
in later processing stages.

## NHGIS table layout

NHGIS calls selections such as whole-area, urban, and rural counts _breakdowns_. Within each
dataset and geography level, `breakdownAndDataTypeLayout` controls whether those breakdowns and
data types appear together in a population table or in separate files. The resulting tables are
CSV files inside the downloaded ZIP archive, with separate tables for different datasets and
geography levels regardless of this setting.

The [NHGIS extract documentation][nhgis-extract-fields] requires the layout setting when multiple
breakdowns or data types are present. However, dataset metadata for
[`1980_STF1`](https://api.ipums.org/metadata/nhgis/datasets/1980_STF1?version=2) and
[`1990_STF1`](https://api.ipums.org/metadata/nhgis/datasets/1990_STF1?version=2) reports
`hasMultipleDataTypes: false` (API access requires an IPUMS key).

Because these datasets have one data type, selecting a single breakdown leaves nothing for this
setting to split or combine. NHGIS may therefore omit the layout field in its description of the
completed extract even when the request specified `single_file`.

Retrieval accepts an omitted layout for these two datasets when each has at most one selected
breakdown, treating an omitted breakdown selection as the whole-area default. With multiple
breakdowns, NHGIS must still report the requested layout. In either case, the selected tables,
geographies, years, and breakdowns must match, and the saved submission record retains the
original request.

The requested `csv_header` format includes two header rows: column names followed by full
descriptions. NHGIS's `csv_no_header` still includes column names; it omits the description row.

## NHGIS 1980 geographic subareas

The `TOTAL_AND_SUBAREA_BREAKDOWNS_1980` codes come from NHGIS's `1980_STF1` dataset metadata. In
the `breakdowns` list, the entry named `bs03` describes geographic subareas and supplies these
`breakdownValues`:

| Request code  | NHGIS description |
| ------------- | ----------------- |
| `bs03.ge0000` | Total area        |
| `bs03.ge0100` | Urban             |
| `bs03.ge0800` | Rural             |

The source is the [1980_STF1 metadata endpoint][1980-metadata], accessed through the authenticated
API described in the
[NHGIS metadata documentation](https://developer.ipums.org/docs/v2/apiprogram/apis/nhgis/).

Codebooks inside each downloaded NHGIS population archive identify the geographic subarea and the
breakdowns actually returned. For example, the tract codebook in
`nhgis/1980/tracts/population.zip` identifies `Total area (0000)`. Read the accompanying codebook
rather than assuming every geographic level returns all three requested breakdowns. Extract-number
prefixes inside archives may vary between downloads.

Because urban and rural counts describe parts of the whole area, adding them to the whole-area
count would count residents twice. Urban and rural do not overlap each other, but before combining
component records, check that they refer to the same geographic area and population category. If a
value is missing, it cannot be assumed to represent zero population.

## Following the code

The `retrieve` stage in [`reproduce.py`](../code/reproduce.py) starts retrieval by calling
`retrieve_raw_data(config, repository)` in
[`retrieve_files.py`](../code/capy_core/retrieve_data/retrieve_files.py), which builds the input
list and applies the configured filename filters. From there, `retrieve_raw_file()` handles each
file, checking an existing copy or downloading a missing one. A new file receives its final name
only after passing the format checks, a local step the code calls _publication_ without uploading
or releasing the file.

For 2010 block queries, `prepare_download_batches_with_2010_counties_first()` puts the required
county tables in a first batch, which the runner downloads before starting the dependent block
queries. Reusing an existing block file needs no county prerequisite, though county files
explicitly selected in the configuration are still checked. The results list includes each
prerequisite once, followed by the other selected files. If a county table is unavailable or
invalid, its dependent block download also fails while unrelated downloads continue, leaving
completed files available for reuse on the next run.

For 2010 PL blocks, `county:*` can return no data even though the
[Census examples](https://api.census.gov/data/2010/dec/pl/examples.html) document that form. In a
Delaware query, `get=NAME,P001001`, `for=block:*`, and `in=state:10 county:* tract:*` returned
HTTP 204 with an empty body. Supplying state, county, and tract as separate `in` parameters gave
the same result. Replacing the county wildcard with `county:001,003,005` returned HTTP 200 and
24,115 block rows totaling 897,934 residents.

For that reason, 2010 block requests list counties explicitly. The code reads the county codes
from the retrieved 2010 county table and saves each state's block response as
`2010/blocks/<state>/state.json` beneath the configured Census folder. Block requests for 2000 and
2020 also retrieve a state at a time, using county wildcards.

The reusable retrieval operations live under
[`capy_core/retrieve_data/`](../code/capy_core/retrieve_data/):

| Module                                                                                   | Responsibility                                                                                               |
| ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| [`retrieve_files.py`](../code/capy_core/retrieve_data/retrieve_files.py)                 | Select inputs, retrieve files in parallel, and recheck pending extracts.                                     |
| [`retrieve_raw_file.py`](../code/capy_core/retrieve_data/retrieve_raw_file.py)           | Reuse or download one file; retry broken transfers and check the file before saving it under its final name. |
| [`census/retrieve_tables.py`](../code/capy_core/retrieve_data/census/retrieve_tables.py) | Prepare county prerequisites, construct Census queries, and download PL/SF1 JSON responses.                  |
| [`nhgis/retrieve_extract.py`](../code/capy_core/retrieve_data/nhgis/retrieve_extract.py) | Submit or resume NHGIS extracts, compare saved requests, and download available archives.                    |
| [`http_transport.py`](../code/capy_core/retrieve_data/http_transport.py)                 | Read HTTP responses in chunks, handle rate limits, and check downloaded byte counts.                         |

[`nhgis/extract_definition.py`](../code/capy_core/retrieve_data/nhgis/extract_definition.py)
translates NHGIS requests and compares them with the prepared extract. All downloads use
[`stage_files.py`](../code/capy_core/stage_files.py) to manage temporary files and move completed
files to their final names.

When NHGIS returns a pending extract, the run saves its extract number and rechecks it after the
initial downloads, as described in the [run guide](../code/README.md#run-retrieval). Those records
also let a later run resume without submitting the extracts again if the wait limit expires or the
run is interrupted.

Before reusing an NHGIS archive, retrieval compares any saved submission with the current request.
A mismatch leaves both files unchanged and reports their paths, so intentionally changed
selections require either a new raw-data directory or removal of both the old archive and its
submission record before rerunning. Without a record, existing archives receive only basic format
checks because there is no saved request against which to verify their selections. Even a matching
record establishes only what was requested, without proving the archive's contents.

Configuration errors identify the YAML file and invalid setting or syntax line, while local
filesystem errors retain the affected filename. NHGIS reports whether submission, status lookup,
or reading extract details failed without including provider text that could contain credentials.
Expected file failures do not stop unrelated files. Unexpected programming errors stop the batch
so they can be diagnosed.

## Basic checks

Requests must have valid settings and distinct destination filenames inside the raw-data
directory. A download must return HTTP 200 and produce a nonempty file. When an uncompressed
response supplies `Content-Length`, the saved byte count must match it. The count is not compared
for compressed responses because the HTTP library may decompress them before writing.

For ZIP archives, shapefile ZIPs, and XLSX workbooks, retrieval checks that it can read the list
of files inside and that the list contains at least one file. Census JSON must contain a header
and at least one data row, with the same number of values in every row. Other formats are checked
only for a nonempty file. NHGIS also receives the [request comparison](#nhgis-request-comparisons)
described above.

Census JSON downloads retain the response's formatting because retrieval reads the saved table for
validation without rewriting it. As a result, differences in whitespace can change raw checksums
even when the table values match. Validation also rejects JSON numbers such as `NaN` and infinity.

Failed downloads discard their temporary files, so a partial download cannot be mistaken for a
completed file on the next run. Existing files are never overwritten and receive a lighter check:
archives must still list at least one file, and Census tables must be nonempty and open and close
as a JSON array, but they are not parsed again. A table whose contents were altered after
publication is reported when population processing parses it; tables that no later stage reads are
not rechecked. These checks do not read every file inside an archive, verify population values, or
establish that population records match the boundaries. Those checks belong to population
processing and geographic joins. Retrieval does not compare checksums.

## Sources and coverage

| Source family                         | Files | Role                                                                |
| ------------------------------------- | ----: | ------------------------------------------------------------------- |
| Census API response tables            |   676 | All four geography levels in 2000, 2010, and 2020, plus 2020 places |
| TIGER boundary archives               |   523 | Corresponding modern census boundaries and 2020 places              |
| Original TIGER 1992 county archives   |     5 | Reconstruction of omitted 1980 BNA outlines                         |
| Original 1990 block references        |    12 | STF1B and PL evidence for unmatched empty land blocks               |
| NHGIS extract archives                |    14 | 1980/1990 populations and boundaries                                |
| Published population reference tables |     8 | Published totals for checking population counts and definitions     |
| March 2020 metro delineation workbook |     1 | Metro membership definitions for geographic assignment              |

The full configuration requests 1,239 files across the source families above. Its 676 modern
population tables cover the 50 states, DC, and Puerto Rico, with one response per state for each
required year and geography level, including 2020 places. The 2000 block-group tables use SF1,
while the other modern population inputs use PL 94-171.

For boundaries, the 2000 and 2010 census years use the recorded TIGER2010 products, and 2020 uses
TIGER2020. Historical county boundaries come from NHGIS TL2008 products, while the supported
tract/BNA, block-group, and block boundaries for 1980/1990 use the recorded TL2000 products.

Supported graph inputs are counties and tracts in 1980, and counties, tracts, block groups, and
blocks in 1990. Puerto Rico boundaries for 1980/1990 and 1980 block/block-group boundaries are
unavailable in this supported source collection. Supplemental 1980 population tables do not
establish availability of corresponding polygons. These unavailable combinations are not failed
downloads and must not be interpreted as empty or zero-population geography.

## Reusing local files

The pipeline checks each file in its configured folder before downloading it. To continue a
previous run, use the same command and configuration: files that pass the basic checks are reused,
and missing files are downloaded.

If you downloaded data elsewhere, place it at the location the configuration expects. For example,
with `raw_data_directory: data/raw` and `census_boundary_files: tiger`, the 2020 Delaware tract
boundary ZIP belongs at:

```text
data/raw/tiger/2020/tracts/tl_2020_10_tract.zip
```

Use `--offline` to check that the selected inputs are available without downloading anything:

```bash
uv run --locked python code/reproduce.py --config code/configs/small_example.yaml \
    --offline retrieve
```

Missing or invalid files are reported as failures, and existing files are never overwritten.
Changing the folder settings does not move files already on disk, so move them yourself if you
want to reuse them under a different layout.

## Published raw checksums

The raw-data collection is too large to publish on GitHub. Instead, maintainers publish SHA-256
checksums in [`data/raw_checksums.sha256`](../data/raw_checksums.sha256) as a reference for
investigating differences in replication results. Each checksum identifies a file's exact bytes,
allowing comparison with a local copy. The pipeline neither generates this list nor compares
downloaded files with it automatically, and checksum comparison is not required to run the
pipeline.

Maintainers can record the completed raw inputs explicitly:

```bash
uv run --locked python code/record_raw_checksums.py \
    --config code/configs/replication.yaml
```

The command writes SHA-256 digests to `raw_checksums_file`, or the path supplied by `--output`,
alongside filenames relative to the configured `raw_data_directory` (`data/raw/` by default).
Entries follow destination-path order and describe the files actually present, with an error if
any selected input cannot be read. The command selects filenames from the request definitions
without downloading files or requiring the saved county tables used by 2010 block retrieval. Use
the full configuration for the published reference, since a subset configuration records only that
subset.

NHGIS can change archive names or packaging between extracts and accounts. A different archive
checksum establishes different bytes, not necessarily different population values. If replication
results differ, investigate the relevant data contents as well as the archive packaging.

[published-requests]: ../code/capy_core/retrieve_data/census/build_published_file_requests.py
[nhgis-extract-fields]: https://developer.ipums.org/docs/v2/workflows/create_extracts/nhgis_data/#data-extract-request-fields
[1980-metadata]: https://api.ipums.org/metadata/nhgis/datasets/1980_STF1?version=2
[working-paper-56]: https://www.census.gov/library/working-papers/2002/demo/POP-twps0056.html
