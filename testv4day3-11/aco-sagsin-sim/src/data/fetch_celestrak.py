from __future__ import annotations

import httpx
import time
from typing import List

from ..config import load_config
from ..types import Node
from .cache import load_cache, save_cache

API = "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=json"


def _norm_lon(lon: float) -> float:
    return ((lon + 180) % 360) - 180


def fetch() -> List[Node]:
    cfg = load_config()
    cached = load_cache("celestrak_active")
    if cached is not None:
        return [Node(**n) for n in cached]

    nodes: List[Node] = []
    if cfg.offline or not cfg.enable_sat:
        return nodes

    timeout = httpx.Timeout(cfg.http_timeout_sec)
    for attempt in range(cfg.http_retries):
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.get(API)
                resp.raise_for_status()
                data = resp.json()
                for sat in data:
                    # Approximate altitude: use mean motion or default 550km if missing
                    alt_m = float(sat.get("apogee", 550 * 1000))
                    # Use no position from GP; we only seed satellites roughly on equator at random longitudes
                    # For simplicity, place a ring; real-time TLE -> position requires SGP4, omitted for now
                    # Here we distribute around longitudes by NORAD_CAT_ID modulo
                    try:
                        norad = int(sat.get("NORAD_CAT_ID", 0))
                    except Exception:
                        norad = 0
                    lon = _norm_lon((norad % 360) - 180)
                    lat = 0.0
                    nodes.append(Node(id=-1, kind="sat", lat=lat, lon=lon, alt_m=alt_m))
                break
        except Exception:
            if attempt + 1 == cfg.http_retries:
                break
            time.sleep(cfg.backoff_factor * (2**attempt))
    save_cache("celestrak_active", [n.__dict__ for n in nodes])
    return nodes
