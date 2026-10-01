"""Write GerryChain JSON into ZIP members and read graphs without extracting files."""

import json
import shutil
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from gerrychain import Graph
from networkx.readwrite import json_graph


def write_graph_json(graph: Graph, output_path: Path) -> None:
    """Save a graph with stable node/edge ordering using GerryChain's JSON serializer.

    Args:
        graph (Graph): Graph with JSON-compatible attributes. Polygons are omitted.
        output_path (Path): Temporary JSON path owned by the selection archive builder.

    Raises:
        OSError: Writing fails; the caller owns cleanup of incomplete files.
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

    ordered_graph.to_json(str(output_path))


def write_file_to_archive(archive: ZipFile, member_path: Path, temporary_directory: Path) -> None:
    """Stream a completed temporary file into a compressed ZIP member with a fixed timestamp.

    Args:
        archive (ZipFile): Open ZIP, owned by the caller and written by one process only.
        member_path (Path): Path relative to temporary_directory, also used as the ZIP member name.
        temporary_directory (Path): Selection-owned folder containing the completed file.

    Raises:
        OSError: Reading the temporary file or writing the ZIP fails.
    """
    with (
        (temporary_directory / member_path).open("rb") as source,
        archive.open(
            build_zip_member(member_path.as_posix()), "w", force_zip64=True
        ) as destination,
    ):
        shutil.copyfileobj(source, destination)


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
