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
        # Preserve any existing name from the source; otherwise assign a friendly default
        name = getattr(n, "name", "") or f"{n.kind}-{i}"
        out.append(Node(id=i, kind=n.kind, lat=n.lat, lon=n.lon, alt_m=n.alt_m, name=name))
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

    # bbox filter (pre)
    nodes = filter_bbox(nodes, cfg.bbox)

    # clustering
    if cfg.enable_clustering and nodes:
        nodes = dbscan_cluster(nodes, cfg.cluster_radius_km)

    # continent filter & limiting
    def continent_bbox(name: str) -> dict[str, float]:
        name = (name or "").lower()
        # coarse bounding boxes for continents/regions
        boxes = {
            "asia": {"min_lat": 1, "max_lat": 81, "min_lon": 26, "max_lon": 180},
            "europe": {"min_lat": 35, "max_lat": 72, "min_lon": -25, "max_lon": 45},
            "africa": {"min_lat": -35, "max_lat": 38, "min_lon": -20, "max_lon": 55},
            "north_america": {"min_lat": 7, "max_lat": 83, "min_lon": -170, "max_lon": -50},
            "south_america": {"min_lat": -56, "max_lat": 13, "min_lon": -82, "max_lon": -35},
            "america": {"min_lat": -56, "max_lat": 83, "min_lon": -170, "max_lon": -35},
            "oceania": {"min_lat": -50, "max_lat": 0, "min_lon": 110, "max_lon": 180},
        }
        return boxes.get(name, cfg.bbox)

    if getattr(cfg, "continent", None):
        nodes = filter_bbox(nodes, continent_bbox(cfg.continent))

    # enforce node_limit with type_mix if provided
    limit = int(getattr(cfg, "node_limit", 0) or 0)
    mix = getattr(cfg, "type_mix", None)
    if limit > 0 and nodes:
        if mix:
            # normalize mix and compute per-kind quotas
            kinds = ["sat", "air", "ground", "sea"]
            total = sum(float(mix.get(k, 0.0)) for k in kinds)
            quotas = {k: int(round(limit * (float(mix.get(k, 0.0)) / total))) if total > 0 else 0 for k in kinds}
            # greedy selection per kind, then fill remaining from any kind
            selected: list[Node] = []
            remaining = limit
            by_kind: dict[str, list[Node]] = {k: [n for n in nodes if n.kind == k] for k in kinds}
            for k in kinds:
                take = min(len(by_kind[k]), max(0, quotas[k]))
                selected.extend(by_kind[k][:take])
                remaining -= take
            if remaining > 0:
                # fill remainder from remaining nodes regardless of kind, avoiding duplicates
                picked_ids = {id(n) for n in selected}
                for n in nodes:
                    if id(n) in picked_ids:
                        continue
                    selected.append(n)
                    remaining -= 1
                    if remaining <= 0:
                        break
            nodes = selected[:limit]
        else:
            nodes = nodes[:limit]

    if not nodes:
        # fallback tiny toy set
        nodes = [
            Node(id=-1, kind="ground", lat=0.0, lon=0.0, alt_m=0.0, name="ground-0"),
            Node(id=-1, kind="ground", lat=0.1, lon=0.1, alt_m=0.0, name="ground-1"),
            Node(id=-1, kind="sat", lat=0.2, lon=0.2, alt_m=550000.0, name="sat-2"),
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
