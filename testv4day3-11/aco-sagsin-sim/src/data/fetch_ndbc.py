from __future__ import annotations

import httpx
import time
from typing import List

from ..config import load_config
from ..types import Node
from .cache import load_cache, save_cache

API = "https://www.ndbc.noaa.gov/data/stations/station_table.txt"


def _norm_lon(lon: float) -> float:
    return ((lon + 180) % 360) - 180


def fetch() -> List[Node]:
    cfg = load_config()
    cached = load_cache("ndbc")
    if cached is not None:
        return [Node(**n) for n in cached]

    nodes: List[Node] = []
    if cfg.offline or not cfg.enable_sea:
        return nodes

    timeout = httpx.Timeout(cfg.http_timeout_sec)
    for attempt in range(cfg.http_retries):
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.get(API)
                resp.raise_for_status()
                text = resp.text.splitlines()
                # Skip header lines starting with "#"
                for line in text:
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split("\t")
                    if len(parts) < 7:
                        continue
                    try:
                        lat = float(parts[6])
                        lon = float(parts[7])
                    except Exception:
                        continue
                    nodes.append(Node(id=-1, kind="sea", lat=lat, lon=_norm_lon(lon), alt_m=0.0))
                break
        except Exception:
            if attempt + 1 == cfg.http_retries:
                break
            time.sleep(cfg.backoff_factor * (2**attempt))
    save_cache("ndbc", [n.__dict__ for n in nodes])
    return nodes
