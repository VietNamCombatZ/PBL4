from __future__ import annotations

from typing import Iterable

from ..types import Node


def in_bbox(n: Node, bbox: dict[str, float]) -> bool:
    return (
        bbox["min_lat"] <= n.lat <= bbox["max_lat"]
        and bbox["min_lon"] <= n.lon <= bbox["max_lon"]
    )


def filter_bbox(nodes: Iterable[Node], bbox: dict[str, float]) -> list[Node]:
    return [n for n in nodes if in_bbox(n, bbox)]
