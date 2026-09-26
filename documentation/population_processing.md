# Population-table processing

This guide explains how to turn downloaded population tables into the files used for geographic
joins, what the saved columns mean, and which population checks run before saving. Processing uses
NHGIS STF1 tables for 1980 and 1990 and Census PL/SF1 tables for 2000, 2010, and 2020, preserving
every source record, including units with no residents. Matching those records to boundaries and
repairing geometries follow in a separate stage.

## Contents

- [Run processing](#run-processing)
- [Read the outputs](#read-the-outputs)
- [Population definitions and checks](#population-definitions-and-checks)
- [Historical NHGIS tables](#historical-nhgis-tables)
- [Geographic identifiers](#geographic-identifiers)
- [Reruns and incomplete runs](#reruns-and-incomplete-runs)
- [Follow the code](#follow-the-code)

## Run processing

After choosing the inputs in a YAML configuration, use that same configuration to retrieve and
process them. For example, run the Delaware tract example from the repository root:

```bash
uv run --locked python code/reproduce.py --config code/configs/small_example.yaml
uv run --locked python code/process_population.py --config code/configs/small_example.yaml
```

The first command retrieves Delaware's 2020 tract population and boundaries, together with the
state tables and published totals needed to check the population counts. The second reads the
population inputs and saves the processed tables. If the raw inputs are already in their configured
folders, run the second command directly; processing neither downloads files nor reads boundaries.

To process all supported modern tables, substitute `code/configs/modern_population.yaml` in both
commands. That configuration includes counties, tracts, block groups, and blocks for 2000, 2010,
and 2020, plus the 2020 places used for city selection. The full `code/configs/replication.yaml`
configuration also includes counties and tracts in 1980 and all four levels in 1990.

Both commands use the configured years, geography levels, and study-area selections. You can narrow
processing with `file_path_patterns`, but each selected year still needs its state population table
and published reference totals, even when the filter omits them. Modern years use the
resident-population CSV, while 1980 and 1990 use their Census Working Paper 56 E workbooks. If a
required reference is missing, processing stops and reports it.

Population processing runs one state at a time, so the download worker and NHGIS wait settings have
no effect here. The national NHGIS tables are read in smaller batches of rows to avoid holding an
entire block table in memory. Processing still retains the identifiers from earlier batches to
detect duplicate records across the file.

Set `processed_population_directory` in the YAML to choose the output folder, which defaults to
`data/processed/population`. Relative paths start at the repository root. Keep raw and processed
folders separate, with neither inside the other, so processing cannot replace its own inputs.

## Read the outputs

The small example produces these files beneath `processed_population_directory`:

```text
2020/tracts/DE_2020_populations.parquet
2020/states/national_2020_populations.parquet
processing_summary.csv
```

Within each year and geography folder, a file holds one state's units and uses its two-letter
abbreviation in the name. For example, `DE_2020_populations.parquet` contains Delaware's records;
DC and Puerto Rico use `DC` and `PR`. State-level records stay together in a national table so later
comparisons can look up each state's totals. Its filename uses `national` in place of an
abbreviation.

Each output keeps the source columns and adds fields for the study populations, geographic
identifiers, and original record locations:

| Field             | Meaning                                                                     |
| ----------------- | --------------------------------------------------------------------------- |
| `GEOID`           | Modern Census identifier, or historical NHGIS `GISJOIN` preserved verbatim. |
| `TOTPOP`          | Total population.                                                           |
| `WHITE`           | Non-Hispanic White-alone population.                                        |
| `BLACK`           | Non-Hispanic Black-alone population.                                        |
| `POC`             | Total population minus non-Hispanic White-alone population.                 |
| `SOURCE_FILE`     | Input filename relative to the configured raw-data directory.               |
| `SOURCE_ROW`      | Source record position, counting data rows from one after any header rows.  |
| `SOURCE_MEMBER`   | NHGIS CSV filename inside its ZIP; present only in historical outputs.      |
| `CENSUS_YEAR`     | Year of the source population.                                              |
| `CENSUS_DATASET`  | Source dataset: `pl`, `sf1`, `1980_STF1`, or `1990_STF1`.                   |
| `GEOGRAPHY_LEVEL` | Kind of geographic unit, such as `tracts` or `blocks`.                      |

Parquet preserves identifiers as strings and counts as integers, so reading a saved table does not
require special options to retain leading zeros. The files use Zstandard compression, with rows
sorted by `GEOID` and their original positions recorded in `SOURCE_ROW`. To open the Delaware
tract table with pandas:

```python
import pandas as pd

tracts_df = pd.read_parquet(
    "data/processed/population/2020/tracts/DE_2020_populations.parquet",
)
```

For a quick account of the run, open `processing_summary.csv`. It lists the input and output files,
row counts, four study population totals, and the population comparison performed for each table.
These totals describe overlapping populations: a state's residents appear in its county, tract,
block-group, and block tables, so adding totals across levels or years would count them repeatedly.

## Population definitions and checks

The study uses non-Hispanic White-alone and Black-alone counts for `WHITE` and `BLACK`, with
`POC` covering everyone outside the non-Hispanic White-alone category. The
[Census variable guide](raw_source_acquisition.md#census-population-variable-guide) identifies the
source columns for these counts and the additional populations used to check them. Their definitions
come from the Census dictionaries for
[2000 PL](https://api.census.gov/data/2000/dec/pl/variables.html),
[2000 SF1](https://api.census.gov/data/2000/dec/sf1/variables.html),
[2010 PL](https://api.census.gov/data/2010/dec/pl/variables.html), and
[2020 PL](https://api.census.gov/data/2020/dec/pl/variables.html). The selected 2000 block-group
tables use SF1, whose variable names differ from PL but describe the same population categories.

Before deriving the study fields, processing checks the eleven modern source count columns. Each
value must be a nonnegative integer, and the seven race categories must sum to the total population.
Hispanic population cannot exceed that total, while non-Hispanic White and Black counts must fit
within their respective race counts and, together, within the non-Hispanic population. A missing
count causes an error because it does not establish that nobody lives in the unit.

For each modern county, tract, block-group, or block table, all eleven count columns must also sum
to the corresponding state counts. Places receive the checks within each row, but their sums are
not compared with the state because places do not cover all its residents. The summary records
which comparison applies. At the state level, total population is compared with the historical
resident counts in the [Census 2020 apportionment release][resident-totals], using resident
population rather than the different population definition used to apportion representatives.

Agreement shows that the published counts are consistent across geography levels; it does not
provide an independent count of residents or prove that every geographic unit is present. For
example, a missing zero-population unit would leave the state sum unchanged. The next stage compares
population records with boundaries, repairs geometries, and accounts for unmatched records.

## Historical NHGIS tables

Historical tables follow the same output layout, for example
`1980/tracts/AL_1980_populations.parquet`, and cover the 50 states and DC. Puerto Rico is outside
this source collection. Each population ZIP must contain one CSV for the requested geography level,
with an optional second header row describing the columns. Processing recognizes that description
row by its labels so the first population record is retained when the description row is absent.
The saved source columns and record locations let readers trace the derived counts back to the
original archive, including records with zero population.

The `_codebook.txt` beside each CSV defines its count columns. Processing uses the whole-area counts
listed below to derive the study populations. Because the 1980 race categories include Hispanic
residents, their counts must be subtracted to obtain the non-Hispanic White and Black groups.

| Year | `TOTPOP`        | `WHITE`                            | `BLACK`           |
| ---- | --------------- | ---------------------------------- | ----------------- |
| 1980 | `C7L001` (NT1A) | `C9D001 - C9G001` (NT7 minus NT9B) | `C9D002 - C9G002` |
| 1990 | `ET1001` (NP1)  | `ET2001` (NP10)                    | `ET2002` (NP10)   |

Both years use `POC = TOTPOP - WHITE`, and every selected count must be a nonnegative integer.
Blank or nonnumeric values cause an error. For 1980, processing checks that the 15 race counts sum
to total population, the four Hispanic race counts sum to the separate Hispanic total, and each
Hispanic race count fits within its corresponding race group. The ten race and Hispanic-origin
categories in 1990 must likewise sum to the separately reported total. Where the source includes
suppression flags, the output retains them for inspection without interpreting them or replacing
the supplied counts.

State comparisons follow the same principle as the modern tables: counts for smaller units must
sum to their state's counts. This applies to all source count columns and derived study counts for
1980 counties and every supported level below the state in 1990. Processing loads the national
NHGIS state tables before reading the smaller areas, comparing their total, non-Hispanic White,
and non-Hispanic Black counts with
[Census Working Paper 56](https://www.census.gov/library/working-papers/2002/demo/POP-twps0056.html),
Table E-3 for 1980 and Table E-1 for 1990. As with the modern references, these are separate
publications of Census counts rather than independent counts of residents.
The state tables are then reused for these comparisons and saved as the national state outputs,
without reading their archives again.

The exception is 1980 tracts, whose source collection does not cover all residents. Census describes
the expansion to complete national tract/BNA coverage in its [geographic history][tract-history].
Requiring the available tracts to sum to the state would therefore reject the source's actual
coverage. Instead, processing checks that their sums do not exceed the state counts and records
`partial_1980_tract_coverage_bounded_by_state` in the summary. This establishes an upper bound,
but cannot show that every historically available tract is present. Residents outside the source
coverage are not assigned to nearby tracts.

The supported population tables supply whole-area counts, so urban and rural components are not
needed to reconstruct their totals. Archives with extra breakdown columns are rejected to avoid
combining overlapping counts; the
[retrieval guide](raw_source_acquisition.md#nhgis-1980-geographic-subareas) explains those layouts.

## Geographic identifiers

Geographic identifiers stay as strings throughout processing. For modern Census tables, the checks
cover code lengths and digits, the expected state, and uniqueness of the resulting `GEOID`.
Historical tables receive checks of the source year, state and county codes, and nonblank, unique
`GISJOIN` values. Neither reader merges duplicate records.

Historical `GISJOIN` values are copied into `GEOID` exactly as supplied, including special tract
codes, block suffixes, and malformed source labels. Keeping those labels preserves the information
needed to investigate a failed boundary match later. Passing the population checks does not
establish that each label identifies a valid boundary.

Modern 2000 tract codes need one adjustment when constructing `GEOID`. The downloaded API tables use
shortened codes such as `0401`, where TIGER uses `040100`, so processing appends two zeros to
four-digit codes. Six-digit codes are kept as supplied, and all other lengths are rejected. The
original tract column remains unchanged, allowing readers to inspect the adjustment alongside
`SOURCE_FILE` and `SOURCE_ROW`. Census describes the boundary codes in the
[TIGER2010 documentation][tiger-documentation].

## Reruns and incomplete runs

To rebuild the processed tables, rerun the command with the same configuration. Processing first
removes the selected outputs and previous summary, so a failed check cannot leave an older selected
table looking current. As each replacement is written, it receives its final filename only after
the write succeeds. Raw inputs remain unchanged, as do outputs outside the current selection.

If processing fails, the error identifies the affected input or reference and the run stops. Tables
completed earlier in the run may already be present, but `processing_summary.csv` appears only
after every selected table succeeds. Use the configuration to determine which files belong to the
run; the summary provides an account of its completed outputs rather than selecting inputs for
later stages.

## Follow the code

[`process_population.py`](../code/process_population.py) reads the shared
[`PipelineConfig`](../code/capy_core/pipeline_config.py) and starts processing through
`process_population_tables()` in
[`process_tables.py`](../code/capy_core/process_population/process_tables.py). That function selects
the population inputs, removes the selected old outputs, and runs the Census and NHGIS workflows
before saving the summary. Input names come from the retrieval request definitions, so both stages
use the same configured paths.

Within each workflow, [`read_census.py`](../code/capy_core/process_population/read_census.py) or
[`read_nhgis.py`](../code/capy_core/process_population/read_nhgis.py) reads source records, checks
their counts and identifiers, and derives the study populations. The corresponding
[`check_totals.py`](../code/capy_core/process_population/check_totals.py) and
[`check_nhgis_totals.py`](../code/capy_core/process_population/check_nhgis_totals.py) compare those
counts with state and published references. Once the comparisons pass,
[`save_tables.py`](../code/capy_core/process_population/save_tables.py) names and writes the Parquet
table, using the same temporary-file writer as retrieval.

For the meanings of column names used in calculations, start with
[`population_table_columns.py`](../code/capy_core/population_table_columns.py). It separates study
counts (`PopulationColumn`), geographic identifiers and level (`GeographyColumn`), and Census year,
dataset, and record location (`PopulationSourceColumn`). These string enums give Python code
readable names while keeping the saved column labels unchanged.

Source-specific names stay with their definitions. Census retrieval and processing share
[`census/table_columns.py`](../code/capy_core/retrieve_data/census/table_columns.py), while the
historical count and geographic columns are defined in
[`nhgis_columns.py`](../code/capy_core/process_population/nhgis_columns.py) using the downloaded
codebooks. NHGIS dataset and geography selections are named in
[`nhgis/identifiers.py`](../code/capy_core/retrieve_data/nhgis/identifiers.py).

Continue with [boundary–population joining](geography_population_joining.md) to attach these counts
to polygons and inspect geographic exclusions. The join keeps these population inputs unchanged.

[resident-totals]: https://www2.census.gov/programs-surveys/decennial/2020/data/apportionment/apportionment.csv
[tiger-documentation]: https://www2.census.gov/geo/pdfs/maps-data/data/tiger/tgrshp2010/TGRSHP10.pdf
[tract-history]: https://www.census.gov/about/history/historical-censuses-and-surveys/census-programs-surveys/geography/tracts-and-block-numbering-areas.html
