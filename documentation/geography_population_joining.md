# Joining boundaries and population

Run this stage after processing population tables to attach their counts to polygons. It matches
geographic identifiers, repairs invalid geometry, applies documented source corrections, and saves
the records that could not be matched. Keeping those records separate makes coverage visible
without treating an absent population record as evidence that a polygon is empty.

## Contents

- [Run a join](#run-a-join)
- [Read the outputs](#read-the-outputs)
- [Geometry repair](#geometry-repair)
- [Historical corrections](#historical-corrections)
- [Unmatched records and coverage](#unmatched-records-and-coverage)
- [Checks and reruns](#checks-and-reruns)
- [Following the code](#following-the-code)

## Run a join

From the repository root, run the three preparation stages with the same configuration:

```bash
uv run --locked python code/reproduce.py --config code/configs/small_example.yaml \
    retrieve process-population join-geographies
```

The small example joins Delaware's 2020 tracts. Use `code/configs/replication.yaml` for the
complete selection, or edit the [commented configuration](../code/configs/example.yaml) to choose
years and levels. If the raw boundaries and processed population tables are already available,
select only `join-geographies`. The join reads existing files. Study-area assignment, graph
construction, and metric calculation follow in later stages.

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
[population-processing guide](population_processing.md).

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
records. It is empty for other years and levels.

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

For example, Louisiana's 1990 block `199G`, GISJOIN `G2200870030101199G`, has overlapping pieces
that merge under `buffer(0)`, reducing calculated area by about 27.3%, from 79.903 to 58.086
square kilometers. The same block identity remains. Its absence from the population table is
explained by the Census water-block convention, which establishes zero population and housing for
these blocks; the missing match alone would not establish that. See the
[1999 TIGER/Line documentation](https://www2.census.gov/geo/tiger/TIGER1999/tiger99.pdf), printed
pages 4-22 through 4-24.

## Historical corrections

NHGIS's 1980 tract product includes separate tract and block-numbering-area (BNA) layers with
different identifier fields. The reader normalizes each layer before combining them. The county
outline layer supplies context rather than additional tract records and is left out.

The following corrections alter derived geography outputs while leaving the raw files and
processed population inputs unchanged:

| Source issue                                          | Operation                                                                                                                                                                                                              |
| ----------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Twelve omitted 1980 BNAs                              | Reconstruct outlines from original TIGER chains for Putnam FL, Golden Valley ND, Choctaw OK, Iron UT, and Kane UT. Join the existing population records, representing 32,608 people.                                   |
| Richmond NY tract 0164                                | Transfer its 92 people and every retained population component to Kings tract 0164, making that tract's total 1,802. Apply the same transfer to the two county records; New York and national totals remain unchanged. |
| Ottawa OH and Waverly NY placeholders                 | Merge the geometry into tracts 0303 and 0207 respectively. Their residents already belong to those population records, so no population is added.                                                                      |
| Dyersville IA and Hanna WY extra BNAs                 | Merge geometry into BNAs 9901 and 9903 respectively, again without adding population.                                                                                                                                  |
| Kalawao HI county metadata                            | Use county code 005, consistent with GISJOIN and the population record, in place of the conflicting source attribute 009. Geometry and population stay unchanged.                                                      |
| Three conflicting 1990 Maryland/New Jersey attributes | Correct one Maryland county attribute and two New Jersey STFIDs using the agreeing identifiers and original STF1B records. Geometry and population stay unchanged.                                                     |
| Two malformed 1990 Alaska block GISJOINs              | Correct the two known labels only after checking their intact state, county, tract, block, and STFID fields. The records have populations zero and two.                                                                |

To investigate an unmatched population record, first check its identifier against the raw boundary
layers and the original population records. This distinguishes a reading or identifier error from
a polygon missing in the supplied product. For the twelve BNAs above, neither NHGIS's tract layer
nor its BNA layer contains features for the five counties. All twelve identifiers and their total,
White, Black, and POC counts agree with the original 1980 STF1A population records.

The next step is to read the boundary file's source metadata. The NHGIS BNA metadata,
`US_bna_1980.shp.xml`, identifies TIGER/Line 1992 as its source and describes constructing the
1980 features from county files. That points directly to the
[original Census county archives](https://www2.census.gov/geo/tiger/TIGER1992/). The release year
is 1992, but these files retain explicit 1980 geographic assignments; reconstruction uses those
assignments.

The [TIGER 1992 technical documentation][tiger-1992-documentation] explains how to recover an
outline: Record Types 1 and 2 supply line endpoints and intermediate coordinates, while Record
Type 3 identifies the 1980 areas on each side. Lines with the same BNA on both sides lie inside
it; lines separating that BNA from another area form its boundary. All twelve missing identifiers
occur in these records, and their boundary lines form closed outlines.

Reconstruction uses the documented NAD27 coordinates and checks valid geometry, agreement between
the polygon interior and the left/right labels, and absence of overlap with supplied NHGIS
polygons. Together with the population comparison, these checks support adding the outlines and
joining the existing counts without estimating population. They do not establish which NHGIS
processing step omitted the counties or verify every outline against an original paper map.

The Richmond transfer follows the official correction in the
[1980 New York tract report](https://archive.org/details/1980censusofpo8022601unse), section 1,
printed page XII. The transfer retains the original NHGIS record's race and Hispanic-origin
counts, and the tract run verifies those source values before applying it. County-only runs
transfer the same recorded counts. A `POPULATION_CORRECTION` note identifies the affected records:
their `SOURCE_*` fields still identify the original primary row, but their corrected counts are no
longer verbatim values from that row.

For Maryland block `G24003709962558`, the original STF1B geographic-zero record identifies county
037, matching GISJOIN and STFID rather than the boundary's conflicting county attribute 001. The
small offshore polygon does not independently establish county membership. In New Jersey,
`G34003703714301` and `G34003703711103` have malformed STFIDs; their component codes, GISJOINs,
and original STF1B records agree, including populations of seven and 45. The corrections apply
only to these identified source records, not to arbitrary disagreements between fields.

The four parent assignments follow the geographic relationships in the original 1980 STF1A records
and NHGIS hierarchy/place-part tables. Their exact mappings are recorded beside the
implementation: Ottawa `G3901370nodata → G39013700303`, Waverly `G3601070nodata → G36010700207`,
Dyersville `G19005509902 → G19005509901`, and Hanna `G56000709902 → G56000709903`. These
relationships are specific to the source products selected by retrieval and are not general
nearest-polygon rules.

## Unmatched records and coverage

For 1980, untracted county remainders and ship-crew tracts have population records without
ordinary land polygons. Their geographic codes are preserved as strings, not rounded into nearby
land-tract codes. After the documented corrections, 517 such records account for 838,918 people
outside the mapped tract join. County population coverage is broader than mapped tract coverage,
so the stage reports the difference rather than claiming that tracts cover every resident.

Seven 1980 polygons still lack proven population assignments: six boundary-only BNAs in Alaska,
Kansas, Logan OK, Tullahoma TN, Frankfort IN, and Auburn NY, plus the Denver placeholder
identified on the source map as tract 119.01. Those polygons stay in unmatched output with unknown
population. The proposed Auburn relabeling is not applied; matched Cayuga County records carry a
note about the unresolved centroid/boundary conflicts. Denver's possible parent, tract 0047/BG9,
is also unproven.

For 1990 water blocks, the documented three-digit block number ending in `99`, with any permitted
water suffix, establishes the expected absence of a population row. Suffix `Z` identifies ship
crews and is not treated as water. Other empty blocks are identified by exact Census block IDs in
the [original STF1B geographic-zero tables](https://www2.census.gov/census_1990/stf1b/) and
[PL tables](https://www2.census.gov/census_1990/1990_PL94-171/). Population and housing counts
must both be zero. These sources classify unmatched polygons without adding population rows or
changing the NHGIS population table.

Seven zero-population 1990 tract records and two zero-population Washington block records still
lack resolved polygon identities. Their known population is retained in the unmatched population
table. Thirteen boundary-only 1990 block groups have no established population correspondence and
retain unknown population. Ship-crew records at the supported historical levels remain outside the
mapped join, with their population included in the accounting.

One original zero reference conflicts with a populated record: Queens, NY block
`G3600810077398104` (Census ID `36081077398104`). `STF1BXNY.DBF` record 161405 reports 106 people
and 52 housing units, agreeing with NHGIS. `STF1BZNY.DBF` record 198334 repeats that ID with zero
counts and a different centroid and land area. The pipeline excludes this ID from zero
classifications, retains its 106 residents, and records the conflict in `GEOGRAPHY_NOTE`. Why the
original files repeat the identifier remains unknown.

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

## Following the code

The `join-geographies` stage in [`reproduce.py`](../code/reproduce.py) calls
`join_geography_tables()` in
[`join_tables.py`](../code/national_pipeline/join_geographies/join_tables.py). Read that workflow first:
select inputs, read and prepare one boundary table at a time, join and save its states, then write
the summaries. The outer workflow checks that each selected state is processed exactly once.
[`read_boundaries.py`](../code/national_pipeline/join_geographies/read_boundaries.py) reads the sources,
while [`join_population.py`](../code/national_pipeline/join_geographies/join_population.py) repairs
geometry and matches population records. Separate modules handle the specialized 1980 repairs and
the original 1990 empty-block references, keeping those source-specific operations outside the
main join.

[tiger-1992-documentation]: https://assets.nhgis.org/original-data/gis/TIGER_1992_TechDoc.pdf
