# Build graph archives

Run this stage after study-area assignment to turn the selected Census units into connected
population graphs. It writes ZIP archives that downstream analysis can read directly, along with
population accounting that explains which units the graphs retain.

## Contents

- [Run the stage](#run-the-stage)
- [Parallel graph construction](#parallel-graph-construction)
- [Archive parts and repackaging](#archive-parts-and-repackaging)
- [Population filtering and adjacency](#population-filtering-and-adjacency)
- [Centroid coordinates for distance-based metrics](#centroid-coordinates-for-distance-based-metrics)
- [Known boundary overlaps](#known-boundary-overlaps)
- [Population accounting and overlap evidence](#population-accounting-and-overlap-evidence)
- [Sensitivity to changing the outlines](#sensitivity-to-changing-the-outlines)
- [Connecting separate components](#connecting-separate-components)
- [Read an archived graph](#read-an-archived-graph)
- [Accounting and unavailable areas](#accounting-and-unavailable-areas)
- [Checks and reruns](#checks-and-reruns)
- [Follow the code](#follow-the-code)

## Run the stage

With the preceding stages complete, run:

```bash
uv run --locked python code/reproduce.py --config code/configs/small_example.yaml build-graphs
```

The small example builds graphs of 2020 tracts inside Delaware's three counties. Its archive is
`data/graphs/county_2020_2020_tracts_part01.zip`: the first year identifies the study-area
definition, and the second identifies the Census units. The archive contains one graph per county.
The full configuration produces one or more numbered ZIP parts per supported node year and
resolution. Graph construction and archive writing are a single stage.

Set `graph_archive_directory` to change the output folder. Relative paths start at the repository
root, and the folder must be separate from the raw, population, joined-geography, and study-area
folders. Membership checks read one state's polygons at a time. During construction, each worker
reads the polygons for one study area. Download worker settings do not control this stage.

## Parallel graph construction

Set `max_parallel_graphs` to choose how many study areas can be built at once. The default is 4;
use 1 for sequential construction without subprocesses. The national configurations also use 4; a
machine with ample memory can use 28, as below. The small example uses 1 to avoid worker startup
overhead.

```yaml
max_parallel_graphs: 28
```

Each worker reads an area's polygons, builds its connected graph, and saves its JSON and
removed-population CSV. Larger areas start first to reduce the chance of a large block graph
remaining after the other workers finish. The graph progress bar counts completed areas, including
their temporary file writes. More workers increase memory use and compete for disk reads, so
increasing this setting does not guarantee a proportional speedup.

Membership checks and final ZIP assembly remain sequential. After the workers finish, saving and
packaging bars track compression and ZIP parts in stable study-area order. Worker count and
completion order do not change graph calculations, archive member names, or summary order. Each
year/level finishes before the next begins; no worker writes to a shared ZIP.

Temporary JSON and CSV files are kept beneath the graph output directory until the archive is
complete, then removed. On failure or interruption, queued work is cancelled and the stage waits
for running workers before cleaning up. A running area can therefore delay interruption. Only a
fully written ZIP is published. Use an ordinary script or the CLI for parallel runs; direct Python
scripts must put their entry point inside `if __name__ == "__main__":` so spawned workers do not
restart the workflow.

## Archive parts and repackaging

Archives have names such as `cbsa_2020_1990_blocks_part01.zip`. Each part is an ordinary ZIP
containing whole study areas: a graph and its removed-population CSV always stay together. Its
`summary.csv` contains only those areas and records the total number of parts. The reader requires
every consecutively numbered part and rejects repeated area IDs. Max-city, CBSA, and county runs
use the same layout; smaller selections need only `part01`.

The writer groups areas in sorted ID order using their compressed sizes, aiming for 80 MiB per
part with room for headers and summaries. It then verifies that every final ZIP is below 100 MiB.
A single area larger than the target gets its own part; if that part reaches 100 MiB, packaging
stops rather than splitting a graph into an unreadable fragment. This is an archive publication
limit, not a quota on scratch storage.

Graph construction first writes a temporary complete ZIP so packaging can use actual compressed
member sizes. Python's ZIP writer then recompresses the files into parts. Each saved graph and
population CSV is read back and compared with its source before publication; these checks are
local to packaging and do not create checksum manifests. Temporary ZIPs are removed on completion.

To repackage existing archives without rebuilding any graphs or recalculating metrics, run:

```bash
uv run --locked python code/repackage_graphs.py --config code/configs/replication.yaml
uv run --locked python code/repackage_graphs.py --config code/configs/max_city.yaml
```

Only available selections are repackaged. Their original ZIPs stay in place until all replacement
parts pass the content checks and are published. They are then removed. If publication is
interrupted while the original remains, readers prefer that original and the command can be
repeated. An interrupted publication without an original leaves an incomplete part set, which
`build-graphs` rebuilds for that selection. The command writes the combined run summary only when
all configured selections are present. Existing metric values are unchanged; a later metric run
records the new part filenames in its graph-outcome table.

The metric stage discovers parts automatically and continues to produce one result table per year
and level. Old unnumbered ZIPs remain readable, and a resumed graph build repackages them before
reuse. No graph extraction or manual part concatenation is needed.

## Population filtering and adjacency

Each node retains its source geographic ID and the four study counts: `TOTPOP`, `WHITE`, `BLACK`,
and `POC`. `WHITE` and `BLACK` count non-Hispanic residents in the respective race groups; `POC`
counts everyone except non-Hispanic White residents. See the
[population definitions](population_processing.md) for the source-specific derivations.

The graph retains a unit only when `WHITE + BLACK > 0`. Both White–Black and White–POC analysis
use that same graph. Removed units therefore have zero combined White and Black population, but
can contain other residents. Their IDs and counts remain in the archive's `removed_units/` files,
and the summary reports the resulting total/POC population losses. These losses are separate from
unmatched geographic records documented during joining.

GerryChain constructs rook adjacency: two retained polygons are neighbors when their intersection
has positive length. A corner contact alone does not qualify. Full polygons and population counts
are retained; the code does not clip units to the study-area outline or divide their populations.
Areas, centroid coordinates, and lengths use the pipeline's projected metre coordinate system,
`ESRI:102003`.

## Centroid coordinates for distance-based metrics

Nodes carry `centroid_x` and `centroid_y` so distance-based statistics can use the saved graphs
without reloading polygons. The chosen convention for distance-weighted Moran's I is Euclidean
distance between these geometric centroids. They summarize each unit's shape and are not weighted
by where residents live.

We retain this convention even when a centroid falls outside its polygon. Concave shapes, holes,
and separated polygon parts can make a centroid a poor summary of location, so the resulting
weights may poorly represent proximity between residents. This is an accepted limitation of the
method; we do not substitute an interior point for those units. Its frequency and effect on these
data have not been measured. Study-area membership uses interior representative points, and
component connections use full polygon distances, so neither depends on these saved centroids.

Distinct units can also have coincident centroids, making inverse-distance weights undefined. The
metrics stage must handle that case explicitly rather than allowing division by zero. Saving
centroids does not itself check for coincident locations.

## Known boundary overlaps

We treat overlapping polygons as neighbors and retain their source outlines and Census counts. An
overlap is therefore accepted adjacency, not a reason to clip a polygon or remove a connection.
This choice does not establish that the historical outlines agree on the exact location of a
border. Individually invalid polygons still receive the repairs described in the
[geography joining guide](geography_population_joining.md#geometry-repair).

To hide overlap warnings during graph construction, set:

```yaml
warn_on_polygon_overlaps: false
```

The default is `true`; `replication.yaml` sets it to `false`. The setting applies inside each
graph build, including parallel workers, and suppresses only GerryChain's polygon-overlap
warnings. Other warnings and input validation remain active. Changing this setting does not change
geometry, adjacency, population counts, saved graph contents, or metrics.

When warnings are enabled, intersections at or below **0.0001 m² (100 mm²)** remain silent. Larger
intersections are reported, including when a warning also contains smaller pairs. This tolerance
controls reporting only. Overlap area is not used to estimate population or decide whether an edge
belongs in the graph.

### Population accounting and overlap evidence

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
contains 3,393 positive-area pairs, with 235 exceeding the reporting tolerance:

| Inputs                                | Positive overlap pairs | Above 100 mm² |
| ------------------------------------- | ---------------------: | ------------: |
| 1980 counties                         |                     58 |             7 |
| 1980 tracts and BNAs                  |                    219 |           219 |
| 1990 counties                         |                     61 |             7 |
| 1990 block groups                     |                  1,369 |             0 |
| 1990 blocks                           |                  1,686 |             2 |
| 1990 tracts and every 2000–2020 level |                      0 |             0 |

Every observed historical pair also overlaps in the original NHGIS files. The source polygons,
with the existing `buffer(0)` repair applied where invalid, reproduce the joined outlines.
Parallel construction does not introduce these overlaps. All 219 tract-level pairs cross county
boundaries between the separate tract and block-numbering-area (BNA) layers. The largest is 1.09
km² between Fauquier and Stafford counties in the Washington metro; a larger area alone does not
establish that population records are duplicated.

These observations concern retained units within the configured CBSAs. They do not cover
unselected units, units removed by the population filter, boundary gaps, or pairs in different
CBSAs. Counts across separate study areas, years, or resolutions are not additive national totals.

### Sensitivity to changing the outlines

Trimming either side of the larger overlaps preserves final connections and all 15 non-distance
metrics in the tested county and 1990 block graphs. In one Duluth block experiment, a geographic
connection disappears and the component connector restores the same pair as an artificial edge.
County centroid changes affect distance-weighted Moran scores by at most 0.000107 in these tests.
Duluth's corresponding differences are at most 5.5 × 10⁻¹⁴; Chicago's two distance variants were
not recomputed.

For 1980 tracts, trimming across all 33 affected metros preserves counts and recomputed
memberships of retained units, but changes final connections in nine metros. The largest
`capy_exact` change is 0.001174. A larger Moran change in Florence, approximately −0.018489,
arises from a microscopic gap introduced by subtraction; applying a common micrometre or
millimetre precision grid restores the original connection and all non-distance scores. All
connection losses in these tract tests involve overlaps smaller than 50 m², so area alone does not
establish metric insensitivity.

These experiments show that clipping can change adjacency without correcting population counts.
They provide no authoritative replacement border or bound on possible metric error, and national
rankings and longitudinal conclusions have not been reassessed. The pipeline retains the original
overlap connections under the stated adjacency convention rather than applying those trims.

## Connecting separate components

Filtering can separate previously adjacent units, and islands can already be separate in the
source geography. The code connects the remaining components with a minimum-distance spanning
tree. For every candidate component pair, distance means the shortest separation between any of
their full polygons, not their centroids. Equal distances are resolved by the two geographic IDs
in ascending order. A graph with `k` initial components receives exactly `k - 1` added edges.

Every edge records `artificial`. It is `false` for geographic adjacency and `true` for an added
connection. Added edges also record `connection_distance_m` and use `shared_perim: 0.0`, because
connecting components does not create a shared boundary. A zero-distance artificial connection is
possible when components meet only at a point. Removing artificial edges recovers the retained
units' geographic adjacency, so a second original-graph archive is unnecessary.

The implementation compares component pairs as needed by Prim's algorithm and stores only the best
remaining connections. Highly fragmented graphs still require many distance comparisons. Workers
parallelize different study areas; the component-connection calculation within one graph remains
sequential.

## Read an archived graph

From Python with `code/` on the import path, load a member without extracting the ZIP:

```python
from pathlib import Path
from capy_core.build_graphs.graph_archives import read_graph_from_archive

graph = read_graph_from_archive(
    Path("data/graphs/county_2020_2020_tracts_part01.zip"),
    "graphs/county_10001.json",
)
print(graph.number_of_nodes(), graph.number_of_edges())
```

The returned object is a GerryChain `Graph`. JSON members are written by `Graph.to_json()` and can
also be extracted and read with `Graph.from_json()`. Because those GerryChain methods accept
filenames, each worker saves a temporary JSON file for ZIP assembly. Direct archive reading uses
the same NetworkX adjacency decoder and GerryChain's `Graph.from_networkx()` conversion.
Geometries remain in the joined GeoParquet inputs rather than being repeated in each graph.

The graph's metadata identifies its study area, definition vintage, Census year and resolution,
selected county or place, county membership, and population accounting. County and place IDs
retain their separate meanings. Missing optional values are saved as JSON `null`.

## Accounting and unavailable areas

Each archive contains:

| Member                              | Contents                                                                                                             |
| ----------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `graphs/{study_area_id}.json`       | Connected graph for an area with retained units.                                                                     |
| `removed_units/{study_area_id}.csv` | IDs and all four counts for units removed by the population filter.                                                  |
| `summary.csv`                       | Outcomes for this part, total part count, graph filenames, node/edge counts, and input/retained/removed populations. |

Summary statuses distinguish four outcomes:

- `ready`: a nonempty connected graph was written, including a single-node graph where applicable.
- `no_units_selected`: assignment selected no units; counts are zero and there is no graph member.
- `no_units_after_population_filter`: assignment selected units, but none had positive
  White-plus-Black population. There is no graph member, and the removed-unit file accounts for
  all selected residents.
- `historical_coverage_unavailable`: the area is outside supported historical coverage. Counts
  remain blank rather than becoming estimates of zero, and there is no graph member.

An empty outcome does not mean the city has no residents. At county resolution, for example, a
city can contain no county representative point and therefore receive no county node. This happens
before the White–Black filter. An area emptied by that filter has
`no_units_after_population_filter` status.

A graph's input counts equal retained plus removed counts for every population column. Counts
across different study areas or resolutions can describe overlapping residents and must not be
summed as though they formed one national population.

## Checks and reruns

Before construction, the stage requires definitions at the configured vintage, a completed
assignment summary, and every expected state's membership table. It repeats the representative-
point selection against each complete joined state table and compares every area/ID/count row with
the saved memberships. This catches newly included or omitted polygons, even for areas previously
marked empty. It then reconciles those memberships with the assignment summary.

Construction reads each area's polygons by geographic ID, checking their populations and selection
metadata again before filtering. It checks population conservation, connectivity, and the number
of added edges. These checks do not resolve upstream historical exclusions or independently rerun
city selection.

Reruns reuse completed year/level selections after checking their inventories, ZIP readability,
area coverage, and input population counts against the current assignments. A failed run therefore
keeps earlier completed work. Missing or incomplete selections are rebuilt, while selections
outside the current configuration are left untouched. The stage removes the run-completion summary
at startup and writes it again only after all requested selections finish.

Reusing an archive does not reconstruct its edges or compare its saved centroids against current
polygons. If input shapes or graph-construction methods change, set `rebuild_graphs: true` in the
YAML to replace the selected graphs. The default is `false`. Membership/accounting differences
stop reuse with an instruction to rebuild; passing those checks alone does not detect every
upstream change. Change the setting back to `false` after an intentional rebuild to resume
normally.

Keep source files stable during a run. New worker pools import Python modules from disk, so a
checkout, rebase, or file reorganization while the process is active can interrupt later
selections even when the parent process already loaded its code.

ZIP members use stable ordering and timestamps. Rebuilding unchanged inputs with the same
configuration and software produces the same contents. Run settings remain in the repository's
YAML configurations, and `uv.lock` records the dependency versions. Final publication checks must
still reconcile the chosen configuration and all its upstream outputs, including documented
geographic limitations. The presence of a ZIP or summary alone does not establish publication
acceptance.

## Follow the code

[`run_build.py`](../code/capy_core/build_graphs/run_build.py) coordinates selected inputs, archive
publication, and accounting.
[`build_area_graph.py`](../code/capy_core/build_graphs/build_area_graph.py) builds and saves each
worker's area files. [`read_inputs.py`](../code/capy_core/build_graphs/read_inputs.py) reconciles
saved memberships with joined polygons.
[`construct_graph.py`](../code/capy_core/build_graphs/construct_graph.py) owns population
filtering and geographic adjacency, while
[`connect_components.py`](../code/capy_core/build_graphs/connect_components.py) chooses the
additional polygon connections.
[`graph_archives.py`](../code/capy_core/build_graphs/graph_archives.py) owns GerryChain
serialization and direct archive reading.

[`archive_parts.py`](../code/capy_core/build_graphs/archive_parts.py) packages whole areas and
checks unchanged contents.
[`archive_inventory.py`](../code/capy_core/build_graphs/archive_inventory.py) checks part
completeness for both graph resumption and metric reading.
