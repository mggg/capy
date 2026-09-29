# Joining boundaries and population

Run this stage after processing population tables to attach their counts to polygons. It matches
geographic identifiers, repairs invalid geometry, applies documented source corrections, and saves
the records that could not be matched. Keeping those records separate makes coverage visible
without treating an absent population record as evidence that a polygon is empty.

## Contents

- [Run the stage](#run-the-stage)
- [Read the outputs](#read-the-outputs)
- [Geometry repair](#geometry-repair)
- [Source corrections and unmatched records](#source-corrections-and-unmatched-records)
- [Checks and reruns](#checks-and-reruns)
- [Stage workflow and function responsibilities](#stage-workflow-and-function-responsibilities)

## Run the stage

From the repository root, run the three preparation stages with the same configuration:

```bash
uv run --locked python code/reproduce.py --config code/configs/small_example.yaml \
    retrieve process-population join-geographies
```

The small example joins Delaware's 2020 tracts and the counties that define its study areas. Use
`code/configs/replication.yaml` for the complete selection, or edit the [commented
configuration](../../code/configs/example.yaml) to choose years and levels. If the raw boundaries
and processed population tables are already available, select only `join-geographies`. The join
reads existing files. Study-area assignment, graph construction, and metric calculation follow in
later stages.

As in population processing, filename patterns narrow the run. Include both population and
boundary requests for each selected year and level. For a statewide modern run, select that
state's population table and boundary ZIP. County boundaries come in a national ZIP, from which
the selected states are read. Historical archives cover the 50 states and DC together. National
state population references support population checks and do not themselves become joined
geography outputs.

Historical joins have two additional source dependencies. The 1980 tract/BNA join uses five
original TIGER 1992 county archives to reconstruct omitted outlines. For 1990 blocks, ten original
STF1B disc archives and the California and Connecticut PL tables establish empty land blocks
omitted from NHGIS population tables. Retrieval requests these only for the corresponding year and
level. If these references are missing, rerun retrieval with the same configuration. When
restricting downloads with filename patterns, include the required reference folders as well.

## Read the outputs

Set `joined_geography_directory` in the YAML to choose the output folder, which defaults to
`data/processed/geography`. Relative paths start at the repository root. For the small example,
the join writes:

```text
data/processed/geography/
  2020/counties/
    DE_2020_geography.parquet
    DE_2020_unmatched_population.parquet
    DE_2020_unmatched_boundaries.parquet
  2020/tracts/
    DE_2020_geography.parquet
    DE_2020_unmatched_population.parquet
    DE_2020_unmatched_boundaries.parquet
  join_summary.csv
  geometry_repairs.csv
```

The geography file is GeoParquet, which stores geometry and its coordinate system along with the
population columns. Read it with `geopandas.read_parquet()`. Each matched unit appears once,
including units with zero population; the later graph stage decides which units become nodes.
Population definitions and source columns follow the
[population-processing guide](02_population_processing.md).

Each state also has two unmatched files, even when they are empty. The population file retains the
complete population record and an `EXCLUSION_REASON`. The boundary file retains the polygon and
source identity, with a reason and a `KNOWN_TOTAL_POPULATION` column. This column is zero when the
source establishes zero and is left blank when population is unknown. Ordinary population columns
are absent from the unmatched boundary file.

`join_summary.csv` has four rows for each state, year, and geography level: one each for `TOTPOP`,
`WHITE`, `BLACK`, and `POC`. Its seven columns identify the year, geography level, state, and
group, followed by input, matched, and unmatched population. Input population must equal matched
plus unmatched population. These groups, years, and geography levels overlap; do not add their
totals together. Inspect the matched and unmatched files for individual records and exclusion
reasons.

To trace a boundary to its source, use `BOUNDARY_SOURCE_FILE`, `BOUNDARY_SOURCE_MEMBER`, and
`BOUNDARY_SOURCE_ID`. Paths start at the configured raw-data directory, and the member identifies
the layer within the ZIP. `BOUNDARY_CORRECTION` records identifier repairs or reconstructed
outlines. For merged fragments, `MERGED_BOUNDARY_SOURCES` identifies the added fragment as
`file!member:ID`, while `BOUNDARY_PART_COUNT` counts the original features represented by the
resulting polygon. The raw files retain the complete original boundary attributes. For 1990
blocks, `BOUNDARY_CENSUS_ID` gives the normalized Census block ID used to compare original Census
records. It is empty for other years and levels. `BOUNDARY_WATER_BLOCK` is true for 1990 blocks
whose number marks a water block (three digits ending in `99`, with an optional suffix from `A` to
`Y`) and false elsewhere.

## Geometry repair

An invalid polygon can contain crossing edges or overlapping pieces. Before joining, the stage
applies Shapely's `buffer(0)` only to invalid geometry, in its original coordinate system. It then
requires every result to be a valid, nonempty polygon or multipolygon and projects the geometry to
the study coordinate system, ESRI:102003. This Albers projection uses meters and is designed for
the continental US. Its area and distance distortion differs outside that region, including Alaska
and Hawaii.

`geometry_repairs.csv` identifies every repaired feature, the original validity problem, and its
area before and after repair in that projection. An area change is a geometric change, not a
population adjustment: matching still uses the same geographic ID, and population counts are never
allocated by the amount of area removed. Repair does not independently establish cartographic
accuracy. See
[Shapely's buffer documentation](https://shapely.readthedocs.io/en/stable/manual.html#object.buffer)
for the operation's behavior.

The [data-decisions guide](data_processing_decisions_and_anomalies.md#geometry-repair) works
through a repaired 1990 Louisiana water block whose area changes while its population does not.

## Source corrections and unmatched records

Some historical boundary products omit, mislabel, or split units that the population tables
contain. The join applies a fixed list of documented corrections to its derived outputs, leaving
the raw files and processed population tables unchanged. A corrected boundary records the change
in `BOUNDARY_CORRECTION`, and a transferred population carries a `POPULATION_CORRECTION` note.
Records still unmatched after these corrections stay in the unmatched files with their reason, and
an unmatched boundary keeps unknown population unless a source establishes zero.

The [data-decisions
guide](data_processing_decisions_and_anomalies.md#historical-boundary-corrections) lists each
correction with its source evidence, and its
[unmatched-records section](data_processing_decisions_and_anomalies.md#unmatched-records-and-coverage)
describes the records that remain unresolved, including 1980 untracted county remainders,
ship-crew records, and 1990 empty blocks.

## Checks and reruns

Before matching, the stage checks unique IDs, boundary components, state, year, geography level,
population arithmetic, and usable geometry. Joins require a single record on each side, and
matched state and county codes must agree. Each state's four study totals are conserved across
matched and unmatched records. A boundary classified as water cannot silently acquire positive
population.

Each file is written under a temporary name and moved to its final name after writing succeeds. At
the start of a rerun, selected output files and the previous summaries are removed, so a failed
run cannot leave old selected results looking current. Other selections remain in their folders.
If processing stops partway through, completed state files can remain, but there is no completed
`join_summary.csv`. Rerun the command to rebuild the selected outputs; this stage does not skip
existing derived files. Raw and processed-population inputs are never modified.

## Stage workflow and function responsibilities

The `join-geographies` stage in [`reproduce.py`](../../code/reproduce.py) calls
`join_geography_tables()` in
[`join_tables.py`](../../code/national_pipeline/join_geographies/join_tables.py). Read that workflow
first. It selects the boundary and population inputs through
[`select_inputs.py`](../../code/national_pipeline/join_geographies/select_inputs.py), removes the
selected old outputs, reads and prepares one boundary table at a time, joins and saves its states,
and then writes the summaries. The outer workflow checks that each selected state is processed
exactly once.

[`read_boundaries.py`](../../code/national_pipeline/join_geographies/read_boundaries.py) reads the
sources and applies the identifier corrections, while
[`join_population.py`](../../code/national_pipeline/join_geographies/join_population.py) repairs
geometry, merges the four 1980 placeholder fragments into their parents, and matches population
records. The remaining source-specific operations stay outside the main join:
[`repair_1980_sources.py`](../../code/national_pipeline/join_geographies/repair_1980_sources.py)
transfers the Richmond tract population and reconstructs the missing 1980 BNA outlines, and
[`read_1990_zero_blocks.py`](../../code/national_pipeline/join_geographies/read_1990_zero_blocks.py)
reads the original 1990 empty-block references.
