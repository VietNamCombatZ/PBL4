from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, List, Dict, Optional, Tuple

NodeKind = Literal["sat", "ground", "air", "sea"]


@dataclass
class Node:
    id: int
    kind: NodeKind
    lat: float
    lon: float
    alt_m: float
    # Optional human-readable name; defaults to empty to maintain back-compat with cached data
    name: str = ""


@dataclass
class Link:
    u: int
    v: int
    latency_ms: float
    capacity_mbps: float
    energy_j: float
    reliability: float
    enabled: bool = True


@dataclass
class GraphState:
    nodes: List[Node]
    links: List[Link]
    # adjacency list for quick lookup
    adj: Dict[int, List[int]]
    # edge attributes map (u,v)->link index
    edge_index: Dict[Tuple[int, int], int]
