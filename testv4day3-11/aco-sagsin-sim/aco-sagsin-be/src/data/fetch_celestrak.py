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
                    # compute a deterministic pseudo-random phase from NORAD id
                    # try to pick a latitude within +/- inclination to better spread satellites off the equator
                    import math

                    # attempt to read inclination (degrees) from common keys
                    incl = 0.0
                    for k in ("inclination", "INCLINATION", "incl"):
                        v = sat.get(k)
                        if v is not None:
                            try:
                                incl = float(v)
                                break
                            except Exception:
                                pass

                    # deterministic angle based on norad
                    theta_deg = (norad * 137) % 360
                    theta = math.radians(theta_deg)
                    # sub-satellite latitude oscillates between +/- inclination; sample it deterministically
                    lat = math.sin(theta) * min(90.0, abs(incl))
                    # longitude choice: distribute ring but offset by another pseudo-random value
                    lon = _norm_lon(((norad * 59) % 360) - 180)
                    name = sat.get("OBJECT_NAME") or (f"SAT-{norad}" if norad else "")
                    nodes.append(Node(id=-1, kind="sat", lat=lat, lon=lon, alt_m=alt_m, name=name))
                break
        except Exception:
            if attempt + 1 == cfg.http_retries:
                break
            time.sleep(cfg.backoff_factor * (2**attempt))
    save_cache("celestrak_active", [n.__dict__ for n in nodes])
    return nodes
