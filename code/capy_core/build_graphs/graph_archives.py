"""Write GerryChain JSON into ZIP members and read graphs without extracting files."""

import json
import shutil
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from gerrychain import Graph
from networkx.readwrite import json_graph

from capy_core.stage_files import stage_file


def write_graph_to_archive(
    archive: ZipFile, member_name: str, graph: Graph, temporary_directory: Path
) -> None:
    """Write a graph with GerryChain's serializer, using one disposable JSON file.

    Args:
        archive (ZipFile): Open output archive owned by the caller.
        member_name (str): JSON member name within the archive.
        graph (Graph): Graph with JSON-compatible attributes. Polygons are omitted.
        temporary_directory (Path): Folder for the temporary JSON required by GerryChain's API.

    Raises:
        OSError: Temporary-file or archive writing fails.
        TypeError: An attribute is not supported by GerryChain's JSON serializer.
    """
    ordered_graph = Graph()
    ordered_graph.graph.update(graph.graph)
    ordered_graph.add_nodes_from((node_id, dict(graph.nodes[node_id])) for node_id in sorted(graph))
    sorted_edges = sorted(tuple(sorted(edge)) for edge in graph.edges)
    ordered_graph.add_edges_from(
        (first_id, second_id, dict(graph.edges[first_id, second_id]))
        for first_id, second_id in sorted_edges
    )

    with stage_file(temporary_directory) as temporary_path:
        ordered_graph.to_json(str(temporary_path))

        with (
            temporary_path.open("rb") as json_file,
            archive.open(build_zip_member(member_name), "w", force_zip64=True) as archive_member,
        ):
            shutil.copyfileobj(json_file, archive_member)


def build_zip_member(member_name: str) -> ZipInfo:
    """Give a compressed member a fixed timestamp so rebuilds do not differ only by clock time.

    Args:
        member_name (str): Name of the member within the ZIP archive.

    Returns:
        ZipInfo: Compressed member with a fixed timestamp and DEFLATED compression.
    """
    member = ZipInfo(member_name, date_time=(1980, 1, 1, 0, 0, 0))
    member.compress_type = ZIP_DEFLATED

    return member


def read_graph_from_archive(archive_path: Path, member_name: str) -> Graph:
    """Read one GerryChain adjacency JSON directly from a ZIP, without extracting it.

    GerryChain.from_json accepts filenames only. This uses the same NetworkX adjacency decoder
    and GerryChain.from_networkx conversion, leaving the archive and filesystem unchanged.

    Args:
        archive_path (Path): Completed graph ZIP archive.
        member_name (str): Graph member listed in the archive's summary.csv.

    Returns:
        Graph: Graph with saved node, edge, and graph attributes; polygon geometry is not stored.

    Raises:
        OSError: The archive cannot be read.
        KeyError: The requested member is absent.
        ValueError: The JSON cannot be decoded. ZIP and NetworkX errors also propagate.
    """
    with ZipFile(archive_path) as archive, archive.open(member_name) as graph_file:
        graph_data = json.load(graph_file)

    return Graph.from_networkx(json_graph.adjacency_graph(graph_data))
