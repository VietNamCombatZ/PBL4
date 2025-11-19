from __future__ import annotations

import httpx
import time
from typing import List

from ..config import load_config
from ..types import Node
from .cache import load_cache, save_cache

API = "https://opensky-network.org/api/states/all"


def _norm_lon(lon: float) -> float:
    return ((lon + 180) % 360) - 180


def fetch() -> List[Node]:
    cfg = load_config()
    cached = load_cache("opensky")
    if cached is not None:
        return [Node(**n) for n in cached]

    nodes: List[Node] = []
    if cfg.offline or not cfg.enable_air:
        return nodes

    timeout = httpx.Timeout(cfg.http_timeout_sec)
    for attempt in range(cfg.http_retries):
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.get(API)
                resp.raise_for_status()
                data = resp.json()
                states = data.get("states", [])
                for st in states:
                    lat = st[6]
                    lon = st[5]
                    alt = st[13] if len(st) > 13 else None
                    if lat is None or lon is None:
                        continue
                    alt_m = float(alt) if alt is not None else 10000.0
                    callsign = (st[1] or "").strip() if isinstance(st, list) and len(st) > 1 else ""
                    nodes.append(
                        Node(id=-1, kind="air", lat=float(lat), lon=_norm_lon(float(lon)), alt_m=alt_m, name=callsign)
                    )
                break
        except Exception:
            if attempt + 1 == cfg.http_retries:
                break
            time.sleep(cfg.backoff_factor * (2**attempt))
    save_cache("opensky", [n.__dict__ for n in nodes])
    return nodes
