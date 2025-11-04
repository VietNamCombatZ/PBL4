from __future__ import annotations

import json
from pathlib import Path
from typing import List

from ..config import load_config
from ..logging_setup import setup_logging
from ..types import Node
from .bounding import filter_bbox
from .clustering import dbscan_cluster
from .fetch_celestrak import fetch as fetch_celestrak
from .fetch_ndbc import fetch as fetch_ndbc
from .fetch_opensky import fetch as fetch_opensky
from .fetch_satnogs import fetch as fetch_satnogs

GEN_DIR = Path("data/generated")


def _assign_ids(nodes: List[Node]) -> List[Node]:
    out: List[Node] = []
    for i, n in enumerate(nodes):
        out.append(Node(id=i, kind=n.kind, lat=n.lat, lon=n.lon, alt_m=n.alt_m))
    return out


def main() -> None:
    setup_logging()
    cfg = load_config()

    nodes: List[Node] = []
    if cfg.enable_ground:
        nodes.extend(fetch_satnogs())
    if cfg.enable_sat:
        nodes.extend(fetch_celestrak())
    if cfg.enable_air:
        nodes.extend(fetch_opensky())
    if cfg.enable_sea:
        nodes.extend(fetch_ndbc())

    # bbox filter
    nodes = filter_bbox(nodes, cfg.bbox)

    # clustering
    if cfg.enable_clustering and nodes:
        nodes = dbscan_cluster(nodes, cfg.cluster_radius_km)

    if not nodes:
        # fallback tiny toy set
        nodes = [
            Node(id=-1, kind="ground", lat=0.0, lon=0.0, alt_m=0.0),
            Node(id=-1, kind="ground", lat=0.1, lon=0.1, alt_m=0.0),
            Node(id=-1, kind="sat", lat=0.2, lon=0.2, alt_m=550000.0),
        ]

    nodes = _assign_ids(nodes)

    GEN_DIR.mkdir(parents=True, exist_ok=True)
    with open(GEN_DIR / "nodes.json", "w", encoding="utf-8") as f:
        json.dump([n.__dict__ for n in nodes], f)

    # create minimal placeholder links.json for convenience (controller will rebuild anyway)
    with open(GEN_DIR / "links.json", "w", encoding="utf-8") as f:
        json.dump([], f)


if __name__ == "__main__":
    main()
