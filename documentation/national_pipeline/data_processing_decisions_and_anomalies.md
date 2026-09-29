# Data processing decisions and anomalies

Read this guide when interpreting results, comparing them with another replication, or deciding
whether a pipeline change would alter the study data. It collects the choices that change what the
saved tables, graphs, and scores contain, together with the source anomalies that required them.
Each entry states the decision, its reason, and its consequence for the data. The numbered stage
guides explain how to run each stage and where its outputs are saved.

## Contents

- [Population definitions](#population-definitions)
- [Source coverage limits](#source-coverage-limits)
- [Geometry repair](#geometry-repair)
- [Historical boundary corrections](#historical-boundary-corrections)
- [Unmatched records and coverage](#unmatched-records-and-coverage)
- [Study-area definitions](#study-area-definitions)
- [Graph construction](#graph-construction)
- [Boundary overlaps](#boundary-overlaps)
- [Metric conventions](#metric-conventions)
- [Figure selections](#figure-selections)

## Population definitions

`WHITE` and `BLACK` count non-Hispanic White-alone and Black-alone residents in every year, and
`POC = TOTPOP - WHITE` counts everyone else, including Hispanic residents of any race. POC is
therefore not a synonym for Black population. White–Black comparisons use the combined White and
Black population as their universe, while White–POC comparisons use total population. Modern Census
tables and the 1990 NHGIS tables supply non-Hispanic counts directly. The 1980 race categories
include Hispanic residents, so processing subtracts the Hispanic White and Black counts. The
[population guide](02_population_processing.md#population-definitions-and-checks) lists the source
columns.

Processing preserves every source record, including units with no residents, and never replaces a
missing count with zero. It uses only whole-area counts, never urban or rural components, and
retains historical suppression flags without interpreting them; see
[historical NHGIS tables](02_population_processing.md#historical-nhgis-tables). Modern 2000 tract
codes are extended to TIGER's six digits when constructing `GEOID`, with the original code kept
beside it; see [geographic identifiers](02_population_processing.md#geographic-identifiers).

## Source coverage limits

Supported graph inputs are counties and tracts in 1980, and all four levels from 1990 onward. The
source collection has no 1980 block or block-group boundaries and no Puerto Rico boundaries for
1980 or 1990. Study areas affected by these gaps receive `historical_coverage_unavailable` with
null counts, which are not estimates of zero population. See
[sources and coverage](01_raw_source_acquisition.md#sources-and-coverage).

The 1980 tract tables do not cover every resident, because national tract/BNA coverage expanded
after 1980. Their sums are therefore checked only as an upper bound on the state totals and
recorded as `partial_1980_tract_coverage_bounded_by_state`. Residents outside that coverage are not
assigned to nearby tracts, so 1980 tract graphs describe the covered population only.

## Geometry repair

Invalid polygons are repaired rather than dropped, and repair never moves population: a repaired
polygon keeps its geographic ID and Census counts even when its area changes. The
[joining guide](03_geography_population_joining.md#geometry-repair) describes the repair
operation, the study projection, and the saved repair log.

For example, Louisiana's 1990 block `199G`, GISJOIN `G2200870030101199G`, has overlapping pieces
that merge under `buffer(0)`, reducing calculated area by about 27.3%, from 79.903 to 58.086
square kilometers. The same block identity remains. Its absence from the population table is
explained by the Census water-block convention, which establishes zero population and housing for
these blocks; the missing match alone would not establish that. See the
[1999 TIGER/Line documentation](https://www2.census.gov/geo/tiger/TIGER1999/tiger99.pdf), printed
pages 4-22 through 4-24.

## Historical boundary corrections

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

The twelve reconstructed BNAs rest on the following chain of evidence, which also shows how to
investigate any unmatched population record. First, check its identifier against the raw boundary
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

## Study-area definitions

Metro membership always comes from the March 2020 Census delineation workbook, micropolitan areas
are excluded, and one definition vintage is used across all population years. A historical
comparison therefore does not also change the enclosing area. A metro study area requires every
county on its roster; a missing county stops the run instead of producing a partial metro. See the
[study-area guide](04_study_area_assignment.md#choose-the-study-areas).

Maximum-city selection uses only 2020 geography. It counts 2020 blocks whose published internal
point lies strictly inside a place, restricted to the counties in the metro, and never prorates
population by polygon area. Census-designated places compete alongside incorporated places, and
ties go to the smallest place GEOID. The selected city keeps its whole boundary, including any part
outside the selecting metro, so its score describes 2020 geography rather than the historical
residents of a modern city outline.

Census units are assigned whole: a unit belongs to a study area when the area's boundary covers the
unit's representative point, including a point exactly on the boundary. Units are never clipped
and their populations never divided, so a unit can belong to several overlapping study areas.
Counts across study areas must not be summed as though they described distinct residents.

## Graph construction

Each graph keeps only units with `WHITE + BLACK > 0`, and both population comparisons use that same
graph, so White–POC results exclude POC residents of removed units. See
[population filtering](05_graph_construction.md#population-filtering-and-adjacency) for how the
archives account for those losses.

Adjacency is rook adjacency between whole retained polygons: two units are neighbors when their
shared boundary has positive length. When filtering or islands leave separate components, a
minimum-distance spanning tree joins them using the shortest distance between full polygons, with
ties broken by geographic ID. A graph with `k` components receives `k - 1` artificial edges, marked
`artificial: true`, and the metrics count them like any other edge.

Distance-weighted Moran scores use each unit's geometric centroid, even when the centroid falls
outside its polygon. How often that happens, and how much it affects the scores, has not been
measured. See
[centroid coordinates](05_graph_construction.md#centroid-coordinates-for-distance-based-metrics).

## Boundary overlaps

We treat overlapping polygons as neighbors and retain their source outlines and Census counts. An
overlap is therefore accepted adjacency, not a reason to clip a polygon or remove a connection.
This choice does not establish that the historical outlines agree on the exact location of a
border.

Population belongs to a Census record identified by its geographic ID, not to an area calculated
from its polygon. When two outlines overlap, the pipeline keeps each record once within its
study-area graph; it does not copy either population into the other record or add residents for
the overlapping patch. Graph inputs require unique IDs, membership rows are reconciled with joined
population tables, and retained plus removed counts must equal the graph's input counts. These
checks establish record-level accounting. They do not independently verify the Census's original
enumeration or prove that each outline precisely locates its record's residents.

The complete CBSA overlap inventory covers all 18 supported year/level combinations and 7,056
area/year/level outcomes. Of those outcomes, 48 lack historical coverage and five have no selected
units; absent inputs do not establish absence of overlaps. Among retained units, the inventory
contains 3,393 positive-area pairs, with 235 exceeding the 100 mm² warning tolerance:

| Inputs                                | Positive overlap pairs | Above 100 mm² |
| ------------------------------------- | ---------------------: | ------------: |
| 1980 counties                         | 58                     | 7             |
| 1980 tracts and BNAs                  | 219                    | 219           |
| 1990 counties                         | 61                     | 7             |
| 1990 block groups                     | 1,369                  | 0             |
| 1990 blocks                           | 1,686                  | 2             |
| 1990 tracts and every 2000–2020 level | 0                      | 0             |

Every observed pair also overlaps in the original NHGIS files, so neither the `buffer(0)` repair
nor parallel graph construction introduces them. All 219 tract-level pairs cross county boundaries
between the separate tract and BNA layers. The largest covers 1.09 km² between Fauquier and
Stafford counties in the Washington metro; a larger area alone does not establish that population
records are duplicated. These observations concern retained units within the configured CBSAs, not
unselected or filtered units, boundary gaps, or pairs in different CBSAs.

Trimming tests show how much the convention can matter. In the tested county and 1990 block graphs,
trimming either side of the larger overlaps preserved every final connection and every
non-distance metric, although in one Duluth block graph a lost geographic connection was restored
only as an artificial edge. County centroid changes moved distance-weighted Moran scores by at most
0.000107 and Duluth's by at most 5.5 × 10⁻¹⁴; Chicago's distance variants were not recomputed. For
1980
tracts, trimming in all 33 affected metros preserved memberships and counts but changed final
connections in nine metros. The largest `capy_exact` change was 0.001174; a larger Moran change of
about −0.018 came from a microscopic gap that the subtraction itself introduced. Every connection
lost in the tract tests involved an overlap smaller than 50 m², so overlap area alone does not
predict metric sensitivity.

These tests show that clipping can change adjacency without correcting population counts. They
provide no authoritative replacement border or bound on metric error, and national rankings and
longitudinal conclusions have not been reassessed under trimming. The pipeline therefore retains
the source overlaps.

## Metric conventions

Spatial evenness and Capy scores use each unit together with its neighbors, $I+A$, as the local
environment. Every saved edge counts equally, including artificial connections, and no edge is
weighted by shared boundary length. The pipeline saves three Capy variants with neighbor weight
one: `aspatial_capy`, `capy` (with quadratic self-pairs), and `capy_exact` (distinct people only).
See [metric formulas](06_metric_computation.md#metric-names-and-formulas).

Moran scores center unit shares on their unweighted mean, so a small unit and a large unit have
equal influence on that step. The negative-Laplacian variant normalizes by the sum of absolute
weights, a project-defined extension rather than the ordinary Moran statistic.

A score that the data cannot define is saved as null with a reason, never as zero, and other
scores for the same graph remain available. Yearly means use a fixed set of areas with a defined
value in every selected, supported year, separately for each metric, comparison, and resolution.
They weight areas equally and apply no population-size threshold. See
[saved tables and yearly averages](06_metric_computation.md#saved-tables-and-yearly-averages).

## Figure selections

The national figures apply their own selections to the pipeline's metric tables without changing
those tables: a population threshold on metros, a fixed cohort per metric of metros with a finite
score in every decade, and the exclusion of five CBSAs whose 1980 tract graphs have only two
nodes. The [figure guide](../figures.md#selections-and-interpretation)
explains both.

[tiger-1992-documentation]: https://assets.nhgis.org/original-data/gis/TIGER_1992_TechDoc.pdf
