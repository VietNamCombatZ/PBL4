from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from ..config import load_config

CACHE_DIR = Path("data/cache")


def load_cache(name: str) -> Any | None:
    p = CACHE_DIR / f"{name}.json"
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        meta = data.get("_meta", {})
        ts = meta.get("ts", 0)
        ttl = load_config().cache_ttl_sec
        if time.time() - ts > ttl:
            return None
        return data.get("payload")
    except Exception:
        return None


def save_cache(name: str, payload: Any) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    p = CACHE_DIR / f"{name}.json"
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"_meta": {"ts": time.time()}, "payload": payload}, f)
