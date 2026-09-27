# Assign study areas

Use this stage after population processing and geographic joining to decide which whole Census
units belong to each county or metropolitan study area. Definitions use one fixed vintage across
the selected population years, so a historical comparison does not also change the enclosing area.
This stage saves the memberships that graph construction will use; it does not remove units based
on race, connect graph components, or calculate metrics.

## Contents

- [Run the stage](#run-the-stage)
- [Choose the study areas](#choose-the-study-areas)
- [Select cities by population](#select-cities-by-population)
- [Assign Census units](#assign-census-units)
- [Read the outputs](#read-the-outputs)
- [Incomplete inputs and reruns](#incomplete-inputs-and-reruns)
- [Follow the code](#follow-the-code)

## Run the stage

Run all five implemented stages with one configuration:

```bash
uv run --locked python code/reproduce.py --config code/configs/small_example.yaml
```

The small example selects 2020 Delaware tracts and the county definitions needed to assign them.
For national work, use `code/configs/replication.yaml` or adapt the
[commented example](../code/configs/example.yaml). If the preceding stages have completed, run
assignment alone:

```bash
uv run --locked python code/reproduce.py --config code/configs/small_example.yaml assign-study-areas
```

The assignment stage reads existing inputs; `offline` and download-worker settings do not change
its behavior.

`study_area_directory` defaults to `data/processed/study_areas`. As with the other top-level paths,
relative paths start at the repository root. Keep this folder separate from the raw, population,
and joined-geography directories. Results are grouped by study-area type and definition year,
for example `data/processed/study_areas/max_city/2020/`.

## Choose the study areas

The `study_area_type` setting controls what each definition represents:

| Setting | Definition |
| --- | --- |
| `county` | Each county in the selected definition-vintage inputs. |
| `cbsa` | The union of all counties belonging to each metropolitan area. |
| `max_county` | Each metro's county with the largest total population. |
| `max_city` | Each metro's Census place with the largest population inside that metro. |

Metro membership comes from the March 2020 Census delineation workbook. Micropolitan areas are
excluded. `study_area_vintage` changes the county boundaries and population used to construct the
areas, but does not change that membership list. Every county on the roster must be present;
a historical vintage that lacks a required county fails instead of constructing a partial metro.
County-only runs can use a subset of states. Metro modes require the complete roster's inputs.

Maximum-city selection supports only the 2020 vintage and includes Census-designated places as
well as incorporated places. It requires 2020 county, place, and block inputs even when graph nodes
are historical tracts. The request builders include those dependencies. Ranking-only blocks need
processed populations and raw internal points; their polygons are joined only when blocks are also
selected as graph nodes. Filename filters can still
remove them, in which case later stages fail rather than treat missing inputs as empty areas.

Definitions distinguish the selecting metro from the selected county or place. Metro-based area
IDs use the metro code, so two metros choosing the same city would remain separate assignments.
`metro_county_codes` records the full metro roster; `county_codes` records the counties actually
intersecting the selected area with positive area. A selected city's counties can extend beyond
its selecting metro. A place identifier never substitutes for a county identifier.

## Select cities by population

The ranking estimates population inside the city/metro intersection using 2020 Census blocks.
A place becomes a candidate when its polygon has positive area inside the metro; touching its
boundary alone is insufficient. For each candidate, the code assigns blocks whose published Census
internal point lies strictly inside the place, then counts the residents of those blocks whose
county belongs to the metro. Population is not prorated by polygon area.

Every block's identity and TIGER population must agree with its processed Census population row.
The assigned blocks must reproduce each candidate city's full published population, including its
portions outside the metro. Ambiguous block-to-place assignments or population mismatches stop the
run. These checks validate the source agreement and assignment calculation; the resulting scores
still use 2020 geography and populations, not historical residents within modern city boundaries.

The greatest population inside the metro wins. Equal positive scores are resolved by the smallest
place GEOID, and the candidate table records the tie rule. A metro without a populated candidate
fails. Maximum-county selection similarly ranks total county population, using the smallest county
code to break a tie. Definitions retain the winning city's or county's **whole boundary**, including
any part of a city outside the selecting metro.

## Assign Census units

For every selected node year and resolution, the code calculates each joined polygon's
representative point in the pipeline's projected coordinate system, `ESRI:102003`. It retains a
unit when the study-area boundary covers that point, including a point exactly on the boundary.
The unit's full population and polygon remain intact. This point is calculated from the polygon;
it differs from the published Census internal point used to rank cities.

Units can belong to more than one overlapping study area. Membership counts and populations must
therefore not be added across study areas or resolutions as if they described distinct residents.
Zero-population units remain in these outputs, and White–Black graph filtering belongs to the
next stage.

Membership uses the matched outputs of geographic joining. It does not resolve or assign population
records that lack boundaries. The [joining guide](geography_population_joining.md) explains those
source limitations and the separate unmatched-record files. A completed membership table is not
proof that historical sources cover every resident. All three join outputs must be available;
county and place definitions additionally require that their unmatched tables are empty.

## Read the outputs

Within each type/year folder, the stage writes:

| File | Contents |
| --- | --- |
| `definitions.parquet` | GeoParquet boundaries, names, definition populations, distinct geographic roles, and selection reasons. |
| `candidates.parquet` | All city or county scores for maximum selection; empty for county and CBSA modes. |
| `city_county_populations.parquet` | Reconciled block population by candidate city and county; empty outside maximum-city mode. |
| `memberships/{year}/{level}/{state}_{year}_memberships.parquet` | Area IDs, Census GEOIDs, all four study counts, and the joined source filename. |
| `summary.parquet` | One status, unit count, and population accounting row per area/year/level. |

The membership filename uses the state's postal abbreviation. Its `geography_file` column starts
at `joined_geography_directory`, allowing graph construction to retrieve the full polygons and
attributes by GEOID. Candidate city scores include both full-city and inside-metro population,
area inside the metro, full mapped city area in square kilometres, and the selected flag.

A summary status of `ready` means at least one unit was selected. When the inputs were read
successfully but no unit's representative point falls inside the area, the status is
`no_units_selected`. Puerto Rico areas for 1980/1990 receive `historical_coverage_unavailable`
because they are outside the supported historical inputs. Their counts are null, not population
estimates of zero. Other missing required states are errors. Empty membership files are written
explicitly so an empty result cannot expose rows left by an earlier run.

## Incomplete inputs and reruns

The command stops with a nonzero exit status if inputs or checks fail. Before starting a run, it
removes the named outputs and membership files for that study-area type and definition vintage.
Other types and vintages remain. This also removes previously selected years or levels from that
same type/vintage folder if the new configuration is narrower.

Each completed file is written through a temporary file, and `summary.parquet` is written last.
An interrupted or failed run can leave some new files, but no completed summary. Downstream work
must require a successful assignment run and use its enumerated memberships rather than searching
for arbitrary old artifacts. Publication verification will additionally reconcile the saved
outputs with the final configuration; the presence of a summary alone does not establish that.

## Follow the code

The command calls `assign_study_areas()` in
[`run_assignment.py`](../code/capy_core/assign_study_areas/run_assignment.py), which selects inputs,
loads definitions, runs the chosen rule, and writes outputs.
[`build_definitions.py`](../code/capy_core/assign_study_areas/build_definitions.py) owns county/metro
construction and candidate ranking.
[`count_city_populations.py`](../code/capy_core/assign_study_areas/count_city_populations.py) reads
Census internal points and reconciles block-based city totals.
[`assign_units.py`](../code/capy_core/assign_study_areas/assign_units.py) validates joined inputs,
selects representative points, and builds membership accounting.
