from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from ..config import load_config

CACHE_DIR = Path("data/cache")


def load_cache(name: str) -> Any | None:
    cfg = load_config()
    # If MongoDB is enabled, try the DB first and fall back to file cache
    if getattr(cfg, "enable_db", False):
        try:
            from .db import read_cache as _db_read  # local import - optional dependency

            db_payload = _db_read(name)
            if db_payload is not None:
                return db_payload
        except Exception:
            # DB not available or some error - fall back to file cache
            pass

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
    # Also attempt to write into MongoDB when enabled; ignore failures
    try:
        cfg = load_config()
        if getattr(cfg, "enable_db", False):
            from .db import write_cache as _db_write

            try:
                _db_write(name, payload)
            except Exception:
                pass
    except Exception:
        pass
