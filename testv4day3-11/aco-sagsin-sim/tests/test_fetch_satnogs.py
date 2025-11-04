from __future__ import annotations

import types

import pytest


def test_fetch_satnogs_handles_lng_and_altitude(monkeypatch):
    # Import the module under test
    import src.data.fetch_satnogs as mod

    # Sample payload from API with variations
    payload = [
        {"lat": 10.0, "lng": 20.0, "altitude": 100.0, "name": "GS-LNG"},
        {"lat": 0.0, "lon": -181.0, "elevation": 50.0, "station_id": "GS-LON"},
        {"lat": None, "lng": 10.0, "altitude": 1.0},  # skipped (missing lat)
        {"lng": 30.0, "altitude": 2.0},  # skipped (missing lat)
    ]

    # Fake httpx client/response
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return payload

    class FakeClient:
        def __init__(self, timeout=None):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url):
            assert url == mod.API
            return FakeResponse()

    # Stub httpx.Client
    import httpx

    monkeypatch.setattr(httpx, "Client", FakeClient)

    # Stub config
    cfg = types.SimpleNamespace(
        offline=False,
        enable_ground=True,
        http_retries=1,
        backoff_factor=0.0,
        http_timeout_sec=5,
    )
    monkeypatch.setattr(mod, "load_config", lambda: cfg)

    # Disable cache IO
    monkeypatch.setattr(mod, "load_cache", lambda *a, **k: None)
    monkeypatch.setattr(mod, "save_cache", lambda *a, **k: None)

    nodes = mod.fetch()
    assert len(nodes) == 2

    n0, n1 = nodes
    # First item uses lng + altitude
    assert n0.kind == "ground"
    assert n0.lat == 10.0
    assert n0.lon == 20.0
    assert n0.alt_m == 100.0
    assert n0.name == "GS-LNG"

    # Second item uses lon + elevation, lon should be normalized from -181 to 179
    assert n1.lat == 0.0
    assert n1.lon == 179.0
    assert n1.alt_m == 50.0
    assert n1.name == "GS-LON"
