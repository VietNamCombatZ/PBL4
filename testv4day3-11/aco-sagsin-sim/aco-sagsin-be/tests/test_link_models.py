from __future__ import annotations

from src.net.link_models import capacity_mbps, fspl_db, latency_ms, snr_linear


def test_capacity_positive():
    snr = snr_linear(fspl_db(10, 2.4e9), 20, -100)
    cap = capacity_mbps(20e6, snr)
    assert cap > 0


def test_latency_positive():
    assert latency_ms(100, 2) > 2
