from pipeline.calculate_metrics import (
    angle_1,
    angle_2,
    property_sum,
    moran,
    edge,
    half_edge,
)
import random
import gerrychain.grid
import gerrychain
import pytest
import glob
import math


def generate_grid(n: int, m: int):
    return gerrychain.grid.create_grid_graph((n, m), False)


def create_odd_grids():
    for i in range(2, 100):
        if i % 2 == 1:
            yield generate_grid(i, i)


def create_even_grids():
    for i in range(2, 100):
        if i % 2 == 0:
            yield generate_grid(i, i)


def create_diverse_grids():
    yield from create_even_grids()
    yield from create_odd_grids()


def create_diverse_graphs():
    yield from create_diverse_grids()
    for filename in glob.glob("cbsas/**/*connected.json"):
        yield gerrychain.Graph.from_json(filename)


def give_random_weights(
    graph: gerrychain.Graph, attr: str, lower_bound: int, upper_bound: int
):
    for node in graph.nodes():
        graph.nodes[node][attr] = random.randint(lower_bound, upper_bound)


def give_checkerboard_pattern(grid: gerrychain.Graph, low_val=40, high_val=60):
    # TODO: make sure this loops over things properly
    for counter, node in enumerate(grid.nodes()):
        if counter % 2 == 0:
            grid.nodes[node]["x_col"] = low_val
            grid.nodes[node]["y_col"] = high_val
        else:
            grid.nodes[node]["x_col"] = high_val
            grid.nodes[node]["y_col"] = low_val

    return grid


@pytest.mark.parametrize("graph", create_diverse_graphs())
def test_propsition_1_c(graph):
    give_random_weights(graph, "x_col", 10, 10)
    give_random_weights(graph, "y_col", 10, 10)

    # Test the first part of the proposition
    angle_1_metric_alt = angle_1(graph, "x_col", "y_col")
    angle_2_metric_alt = angle_2(graph, "x_col", "y_col")
    p_bar = property_sum(graph, "x_col") + property_sum(graph, "y_col")
    assert angle_1_metric_alt == (2 * angle_2_metric_alt) + (0.5 * p_bar)

    # Test the second part of the proposition
    angle_1_metric_same = angle_1(graph, "x_col", "x_col")
    angle_2_metric_same = angle_2(graph, "x_col", "x_col")
    x_bar = property_sum(graph, "x_col")
    assert angle_1_metric_same == (2 * angle_2_metric_alt) + x_bar


@pytest.mark.parametrize("graph", create_diverse_graphs())
def test_uniform_graph_moran(graph):
    for node in graph.nodes():
        graph.nodes[node]["uniform_weight"] = 100

    # Should raise a divide by zero error (undefined)
    with pytest.raises(Exception):
        moran(graph)


@pytest.mark.parametrize("graph", create_diverse_graphs())
def test_uniform_graph_edge_and_half_edge(graph):
    for node in graph.nodes():
        graph.nodes[node]["x_col"] = 40
        graph.nodes[node]["y_col"] = 60

    rho = 40 / 100

    assert edge(graph, "x_col", "y_col") == (1 - rho + rho**2) / (2 + rho - rho**2)
    assert half_edge(graph, "x_col", "y_col") == 0.5


@pytest.mark.parametrize("grid", map(give_checkerboard_pattern, create_odd_grids()))
def test_checkerboard_grid_moran(grid):
    assert math.isclose(moran(grid, "x_col"), -1)


"""
@pytest.mark.parametrize("grid", map(lambda x: give_checkerboard_pattern(x, low_val=0, high_val=1), create_odd_grids()))
def test_perfect_checkerboard_grid_edge(grid):
    assert edge(grid, "x_col") == -1

@pytest.mark.parametrize("grid", map(lambda x: give_checkerboard_pattern(x, low_val=0, high_val=1), create_odd_grids()))
def test_perfect_checkerboard_grid_half_edge(grid):
    assert moran(grid, "x_col") == -1
"""
