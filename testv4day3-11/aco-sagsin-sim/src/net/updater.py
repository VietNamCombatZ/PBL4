from __future__ import annotations

import random
from typing import List

from ..config import load_config
from ..types import GraphState
from .graph import build_graph


def update_epoch(state: GraphState) -> GraphState:
    cfg = load_config()
    # For simplicity, jitter link enabled state to simulate dynamics
    for e in state.links:
        if random.random() < 0.05:
            e.enabled = not e.enabled
    # Could also move air nodes slightly; omitted for brevity
    return state


def rebuild_from_nodes(nodes_json_path: str) -> GraphState:
    import json

    with open(nodes_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    nodes = []
    from ..types import Node

    for n in data:
        nodes.append(Node(**n))
    return build_graph(nodes)
