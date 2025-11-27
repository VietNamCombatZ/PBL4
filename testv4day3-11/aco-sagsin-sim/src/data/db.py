from __future__ import annotations

import time
from typing import Any, Optional, List

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
        self._cache_coll = None
        self._nodes_coll = None
        self._ready = False

    def connect(self) -> bool:
        if not PYMONGO_AVAILABLE:
            return False
        cfg = load_config()
        if not cfg.enable_db:
            return False
        if not cfg.mongo_uri:
            return False
        try:
            self._client = MongoClient(cfg.mongo_uri, serverSelectionTimeoutMS=int(cfg.mongo_connect_timeout_sec * 1000))
            self._client.admin.command("ping")
            self._db = self._client[cfg.mongo_db]
            self._cache_coll = self._db[cfg.mongo_cache_collection]
            self._nodes_coll = self._db[cfg.mongo_nodes_collection]
            self._ready = True
            return True
        except Exception:
            try:
                if self._client:
                    self._client.close()
            except Exception:
                pass
            self._client = None
            self._db = None
            self._cache_coll = None
            self._nodes_coll = None
            self._ready = False
            return False

    def is_ready(self) -> bool:
        if self._ready:
            return True
        return self.connect()

    # Cache payloads -------------------------------------------------
    def read_cache(self, name: str) -> Optional[Any]:
        if not self.is_ready():
            return None
        try:
            doc = self._cache_coll.find_one({"_id": name})
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
        if not self.is_ready():
            return False
        try:
            self._cache_coll.replace_one({"_id": name}, {"_id": name, "payload": payload, "ts": time.time()}, upsert=True)
            return True
        except Exception:
            return False

    # Nodes dataset --------------------------------------------------
    def write_nodes(self, nodes: List[dict]) -> bool:
        if not self.is_ready():
            return False
        try:
            self._nodes_coll.replace_one({"_id": "nodes"}, {"_id": "nodes", "payload": nodes, "ts": time.time()}, upsert=True)
            return True
        except Exception:
            return False

    def read_nodes(self) -> Optional[List[dict]]:
        if not self.is_ready():
            return None
        try:
            doc = self._nodes_coll.find_one({"_id": "nodes"})
            if not doc:
                return None
            return doc.get("payload")
        except Exception:
            return None


_store = _MongoStore()


def available() -> bool:
    return _store.is_ready()


def read_cache(name: str) -> Optional[Any]:
    return _store.read_cache(name)


def write_cache(name: str, payload: Any) -> bool:
    return _store.write_cache(name, payload)


def write_nodes(nodes: List[dict]) -> bool:
    return _store.write_nodes(nodes)


def read_nodes() -> Optional[List[dict]]:
    return _store.read_nodes()
