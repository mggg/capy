# Build graph archives

Run this stage after study-area assignment to turn the selected Census units into connected
population graphs. It writes ZIP archives that downstream analysis can read directly, along with
population accounting that explains which units the graphs retain.

## Contents

- [Run the stage](#run-the-stage)
- [Population filtering and adjacency](#population-filtering-and-adjacency)
- [Centroid coordinates for distance-based metrics](#centroid-coordinates-for-distance-based-metrics)
- [Known boundary overlaps](#known-boundary-overlaps)
- [Metric sensitivity in Washington and Albany](#metric-sensitivity-in-washington-and-albany)
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
`data/graphs/county_2020_2020_tracts.zip`: the first year identifies the study-area definition, and
the second identifies the Census units. The archive contains one graph per county. The full
configuration produces one archive per supported node year and resolution, keeping retries and
individual reads manageable. Graph construction and archive writing are a single stage.

Set `graph_archive_directory` to change the output folder. Relative paths start at the repository
root, and the folder must be separate from the raw, population, joined-geography, and study-area
folders. Membership checks read one state's polygons at a time; construction then reads the polygons
needed for one study area. Neither operation holds the national block collection in memory. Download
worker settings do not control this stage.

## Population filtering and adjacency

Each node retains its source geographic ID and the four study counts: `TOTPOP`, `WHITE`, `BLACK`,
and `POC`. `WHITE` and `BLACK` count non-Hispanic residents in the respective race groups; `POC`
counts everyone except non-Hispanic White residents. See the [population
definitions](population_processing.md) for the source-specific derivations.

The graph retains a unit only when `WHITE + BLACK > 0`. Both White–Black and White–POC analysis use
that same graph. Removed units therefore have zero combined White and Black population, but can
contain other residents. Their IDs and counts remain in the archive's `removed_units/` files, and
the summary reports the resulting total/POC population losses. These losses are separate from
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

Distinct units can also have coincident centroids, making inverse-distance weights undefined.
The metrics stage must handle that case explicitly rather than allowing division by zero. Saving
centroids does not itself check for coincident locations.

## Known boundary overlaps

GerryChain warns whenever polygons overlap by any positive area. Historical NHGIS outlines can
contain microscopic slivers even when each polygon is individually valid. The builder suppresses
warnings for intersections at or below **0.0001 m² (100 mm²)**, measured in `ESRI:102003`. This is
a reporting tolerance: polygons, adjacency, shared-perimeter attributes, and population counts
remain unchanged. Larger intersections still produce warnings, including when the same warning
also contains smaller ones.

Across the CBSA-selected 1990 block groups, all 1,369 overlapping pairs measured below this
threshold; the largest intersection was 55.85 mm². Every overlap was also present in the original
NHGIS shapefile, with the same measured area. The earlier county, El Paso block-group, and
DC–Maryland block examples were also below this threshold. Suppressing these warnings does not
establish that every graph connection is historically correct; it separates negligible overlap
areas from boundary discrepancies that warrant investigation.

The 1980 tract and BNA layers have larger mismatches where their county outlines meet. The CBSA
selection contains 219 overlapping pairs across 33 metros, reaching 1.09 km². These source
mismatches remain visible. Repairing individually invalid polygons with `buffer(0)` does not
resolve disagreement between separate polygons' boundaries.

### Metric sensitivity in Washington and Albany

We retain the source polygons and Census counts for these mismatches. In the Washington and
Albany metros, removing the overlapping area from either source layer preserved every graph
connection and produced only very small changes in centroid-distance scores. This supports
retaining the existing inputs for these cases without claiming that their historical borders
are geometrically correct.

The comparison used the saved 1980 tract graphs for Washington (`cbsa_47900`) and Albany
(`cbsa_10580`), with 12 and seven overlapping pairs respectively. Each metro was tested by
subtracting the overlap from either the BNA polygons or the tract polygons, first for its largest
pair and then for all its overlapping pairs. Neither layer was assumed to be authoritative.
Population counts stayed attached to their original Census records, and repeating the
representative-point assignment confirmed that study-area membership remained unchanged.

All 17 metrics were recalculated for both White–Black and White–POC comparisons. The trimmed
polygons still shared boundaries, so every adjacency-based and aspatial score was unchanged.
Centroids moved by at most 60.62 metres in Washington and 29.82 metres in Albany. Across the
four trimming alternatives and both population comparisons, the largest absolute score changes
were:

| Metro | Largest overlap | Largest absolute metric change after trimming |
| --- | ---: | ---: |
| Washington | 1.090 km² | 0.0000005514 |
| Albany | 0.439 km² | 0.0000010096 |

Both maximum changes occurred in inverse-squared-distance Moran's I for White–POC. These
experiments changed temporary copies only; the pipeline does not apply the tested trims.

A separate stress test removed the graph connections between overlapping polygons while keeping
their shapes, centroids, and populations unchanged. Removing all such connections split each
metro graph into two components, after which the usual component connector restored one removed
edge. With net removals of 11 edges in Washington and six in Albany, White–Black adjacency
Moran's I increased by 0.0031348 and 0.0051020 respectively. Removing a connection therefore has
a larger effect than trimming an overlap while retaining the shared boundary. It represents a
different assumption about which units are neighbors.

These results describe sensitivity to the specified alternatives, not bounds on every possible
boundary correction. They do not establish the correct historical borders, validate the
population-to-boundary correspondence, or measure effects on national rankings and published
conclusions. The other 31 metros with 1980 tract/BNA overlaps were not included in these metric
comparisons, and their larger-overlap warnings remain visible.

## Connecting separate components

Filtering can separate previously adjacent units, and islands can already be separate in the source
geography. The code connects the remaining components with a minimum-distance spanning tree. For
every candidate component pair, distance means the shortest separation between any of their full
polygons, not their centroids. Equal distances are resolved by the two geographic IDs in ascending
order. A graph with `k` initial components receives exactly `k - 1` added edges.

Every edge records `artificial`. It is `false` for geographic adjacency and `true` for an added
connection. Added edges also record `connection_distance_m` and use `shared_perim: 0.0`, because
connecting components does not create a shared boundary. A zero-distance artificial connection is
possible when components meet only at a point. Removing artificial edges recovers the retained
units' geographic adjacency, so a second original-graph archive is unnecessary.

The implementation compares component pairs as needed by Prim's algorithm and stores only the best
remaining connections. Highly fragmented graphs still require many distance comparisons; this stage
has no parallel graph workers yet.

## Read an archived graph

From Python with `code/` on the import path, load a member without extracting the ZIP:

```python
from pathlib import Path
from capy_core.build_graphs.graph_archives import read_graph_from_archive

graph = read_graph_from_archive(
    Path("data/graphs/county_2020_2020_tracts.zip"),
    "graphs/county_10001.json",
)
print(graph.number_of_nodes(), graph.number_of_edges())
```

The returned object is a GerryChain `Graph`. JSON members are written by `Graph.to_json()` and can
also be extracted and read with `Graph.from_json()`. Because those GerryChain methods accept
filenames, writing uses one disposable JSON file. Direct archive reading uses the same NetworkX
adjacency decoder and GerryChain's `Graph.from_networkx()` conversion. Polygon geometries remain in
the joined GeoParquet inputs rather than being repeated in each graph.

The graph's metadata identifies its study area, definition vintage, Census year and resolution,
selected county or place, county membership, and population accounting. County and place IDs retain
their separate meanings. Missing optional values are saved as JSON `null`.

## Accounting and unavailable areas

Each archive contains:

| Member | Contents |
| --- | --- |
| `graphs/{study_area_id}.json` | Connected graph for an area with retained units. |
| `removed_units/{study_area_id}.csv` | IDs and all four counts for units removed by the population filter. |
| `summary.csv` | One outcome per study area, graph filename, node/edge counts, and input/retained/removed populations. |

Summary statuses distinguish four outcomes:

- `ready`: a nonempty connected graph was written, including a single-node graph where applicable.
- `no_units_selected`: assignment selected no units; counts are zero and there is no graph member.
- `no_units_after_population_filter`: assignment selected units, but none had positive
  White-plus-Black population. There is no graph member, and the removed-unit file accounts for
  all selected residents.
- `historical_coverage_unavailable`: the area is outside supported historical coverage. Counts
  remain blank rather than becoming estimates of zero, and there is no graph member.

An empty outcome does not mean the city has no residents. At county resolution, for example,
a city can contain no county representative point and therefore receive no county node. This
happens before the White–Black filter. An area emptied by that filter has
`no_units_after_population_filter` status.

A graph's input counts equal retained plus removed counts for every population column. Counts across
different study areas or resolutions can describe overlapping residents and must not be summed as
though they formed one national population.

## Checks and reruns

Before construction, the stage requires definitions at the configured vintage, a completed
assignment summary, and every expected state's membership table. It repeats the representative-
point selection against each complete joined state table and compares every area/ID/count row with
the saved memberships. This catches newly included or omitted polygons, even for areas previously
marked empty. It then reconciles those memberships with the assignment summary.

Construction reads each area's polygons by geographic ID, checking their populations and selection
metadata again before filtering. It checks population conservation, connectivity, and the number of
added edges. These checks do not resolve upstream historical exclusions or independently rerun city
selection.

Reruns remove the named archives and completion summary for this study-area type and vintage,
including years or levels omitted by a narrower configuration. Other types and vintages remain. Each
new ZIP is written under a temporary name and published only after all its areas succeed. The stage
writes `{type}_{vintage}_summary.parquet` last, after every requested archive completes. A failed
run can leave completed new archives but cannot leave a completed run summary.

ZIP members use stable ordering and timestamps. Rebuilding unchanged inputs with the same
configuration and software produces the same contents. Run settings remain in the repository's YAML
configurations, and `uv.lock` records the dependency versions. Final publication checks must
still reconcile the chosen configuration and all its upstream outputs, including documented
geographic limitations. The presence of a ZIP or summary alone does not establish publication
acceptance. Full-run archive sizes should be measured before choosing the publication grouping.

## Follow the code

[`run_build.py`](../code/capy_core/build_graphs/run_build.py) coordinates selected inputs, archive
publication, and accounting. [`read_inputs.py`](../code/capy_core/build_graphs/read_inputs.py)
reconciles saved memberships with joined polygons.
[`construct_graph.py`](../code/capy_core/build_graphs/construct_graph.py) owns population filtering
and geographic adjacency, while
[`connect_components.py`](../code/capy_core/build_graphs/connect_components.py) chooses the
additional polygon connections.
[`graph_archives.py`](../code/capy_core/build_graphs/graph_archives.py) owns GerryChain
serialization and direct archive reading.
