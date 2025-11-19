from __future__ import annotations

from src.aco.solver import ACO
from src.net.graph import build_graph
from src.types import Link, Node, GraphState


def test_aco_on_toy():
    # a simple triangle 0-1-2 with 0-2 as a longer edge
    nodes = [
        Node(id=0, kind="ground", lat=0, lon=0.0, alt_m=0),
        Node(id=1, kind="ground", lat=0, lon=0.2, alt_m=0),
        Node(id=2, kind="ground", lat=0, lon=0.4, alt_m=0),
    ]
    gs = build_graph(nodes)
    aco = ACO(gs)
    path, cost = aco.solve(0, 2)
    assert path[0] == 0 and path[-1] == 2
