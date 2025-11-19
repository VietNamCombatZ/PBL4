from __future__ import annotations

import time
from typing import Any, Optional

from ..config import load_config

try:
    from pymongo import MongoClient
    PYMONGO_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    MongoClient = None  # type: ignore
    PYMONGO_AVAILABLE = False


class _MongoStore:
    def __init__(self) -> None:
        self._client: Optional[MongoClient] = None
        self._db = None
        self._coll = None
        self._ready = False

    def connect(self) -> bool:
        if not PYMONGO_AVAILABLE:
            return False
        cfg = load_config()
        if not getattr(cfg, "enable_db", False):
            return False
        uri = getattr(cfg, "mongo_uri", None)
        if not uri:
            return False
        try:
            # serverSelectionTimeoutMS expects milliseconds
            self._client = MongoClient(uri, serverSelectionTimeoutMS=int(cfg.mongo_connect_timeout_sec * 1000))
            # quick ping to validate connection
            self._client.admin.command("ping")
            self._db = self._client[cfg.mongo_db or "aco"]
            self._coll = self._db[cfg.mongo_cache_collection or "cache"]
            self._ready = True
            return True
        except Exception:
            # ensure clean state on failure
            try:
                if self._client:
                    self._client.close()
            except Exception:
                pass
            self._client = None
            self._db = None
            self._coll = None
            self._ready = False
            return False

    def is_ready(self) -> bool:
        if self._ready:
            return True
        return self.connect()

    def read_cache(self, name: str) -> Optional[Any]:
        """Return payload or None if not found/expired/unavailable."""
        if not self.is_ready():
            return None
        try:
            doc = self._coll.find_one({"_id": name})
            if not doc:
                return None
            ts = doc.get("ts", 0)
            ttl = load_config().cache_ttl_sec
            if time.time() - ts > ttl:
                return None
            return doc.get("payload")
        except Exception:
            return None

    def write_cache(self, name: str, payload: Any) -> bool:
        if not PYMONGO_AVAILABLE:
            return False
        if not self.is_ready():
            return False
        try:
            self._coll.replace_one({"_id": name}, {"_id": name, "payload": payload, "ts": time.time()}, upsert=True)
            return True
        except Exception:
            return False


_store = _MongoStore()


def read_cache(name: str) -> Optional[Any]:
    return _store.read_cache(name)


def write_cache(name: str, payload: Any) -> bool:
    return _store.write_cache(name, payload)


def available() -> bool:
    return _store.is_ready()
