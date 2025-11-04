from __future__ import annotations

import httpx
import time
from typing import List

from ..config import load_config
from ..types import Node
from .cache import load_cache, save_cache


API = "https://network.satnogs.org/api/stations/"


def _norm_lon(lon: float) -> float:
    return ((lon + 180) % 360) - 180


def fetch() -> List[Node]:
    cfg = load_config()
    cached = load_cache("satnogs")
    if cached is not None:
        return [Node(**n) for n in cached]

    nodes: List[Node] = []
    if cfg.offline or not cfg.enable_ground:
        return nodes

    timeout = httpx.Timeout(cfg.http_timeout_sec)
    # manual retry with backoff
    for attempt in range(cfg.http_retries):
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.get(API)
                resp.raise_for_status()
                data = resp.json()
                for st in data:
                    lat = st.get("lat")
                    lon = st.get("lon")
                    alt = st.get("elevation", 0) or 0
                    if lat is None or lon is None:
                        continue
                    nodes.append(Node(id=-1, kind="ground", lat=float(lat), lon=_norm_lon(float(lon)), alt_m=float(alt)))
                break
        except Exception:
            if attempt + 1 == cfg.http_retries:
                break
            time.sleep(cfg.backoff_factor * (2**attempt))
    save_cache("satnogs", [n.__dict__ for n in nodes])
    return nodes
