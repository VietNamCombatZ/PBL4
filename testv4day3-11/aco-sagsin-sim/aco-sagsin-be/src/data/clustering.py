from __future__ import annotations

from typing import Iterable

import numpy as np
from sklearn.cluster import DBSCAN

from ..types import Node


EARTH_RADIUS_KM = 6371.0


def _to_rad(coords: np.ndarray) -> np.ndarray:
    return np.radians(coords)


def dbscan_cluster(nodes: Iterable[Node], radius_km: float) -> list[Node]:
    arr = np.array([[n.lat, n.lon, n.alt_m] for n in nodes], dtype=float)
    if len(arr) == 0:
        return []
    # Haversine expects [lat,lon] in radians; we ignore altitude for clustering
    latlon = _to_rad(arr[:, :2])
    eps = radius_km / EARTH_RADIUS_KM
    clustering = DBSCAN(eps=eps, min_samples=1, metric="haversine").fit(latlon)
    labels = clustering.labels_
    out: list[Node] = []
    for lbl in np.unique(labels):
        idxs = np.where(labels == lbl)[0]
        group = arr[idxs]
        lat = float(np.mean(group[:, 0]))
        lon = float(np.mean(group[:, 1]))
        alt = float(np.mean(group[:, 2]))
        # normalize lon to [-180,180]
        lon = ((lon + 180) % 360) - 180
        kind = nodes[idxs[0]].kind
        # try to synthesize a name from first member
        base_name = getattr(nodes[idxs[0]], "name", "")
        name = base_name or f"{kind}-cluster-{int(lbl)}"
        out.append(Node(id=-1, kind=kind, lat=lat, lon=lon, alt_m=alt, name=name))
    return out


def grid_cluster(nodes: Iterable[Node], grid_deg: float = 0.1) -> list[Node]:
    buckets: dict[tuple[int, int, str], list[Node]] = {}
    for n in nodes:
        key = (int(n.lat / grid_deg), int(n.lon / grid_deg), n.kind)
        buckets.setdefault(key, []).append(n)
    out: list[Node] = []
    for (_, _, kind), group in buckets.items():
        lat = float(np.mean([g.lat for g in group]))
        lon = float(np.mean([g.lon for g in group]))
        alt = float(np.mean([g.alt_m for g in group]))
        lon = ((lon + 180) % 360) - 180
        base_name = getattr(group[0], "name", "") if group else ""
        name = base_name or f"{kind}-grid"
        out.append(Node(id=-1, kind=kind, lat=lat, lon=lon, alt_m=alt, name=name))
    return out
