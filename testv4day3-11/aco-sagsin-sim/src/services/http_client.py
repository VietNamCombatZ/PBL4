from __future__ import annotations

import httpx

from ..config import load_config


def get_http_client() -> httpx.Client:
    cfg = load_config()
    return httpx.Client(timeout=cfg.http_timeout_sec)
