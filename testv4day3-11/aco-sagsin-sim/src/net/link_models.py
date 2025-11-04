from __future__ import annotations

import math
from typing import Tuple

from ..config import load_config
from ..types import Node

C_KM_PER_MS = 299792.458  # km per second -> 299.792458 km/ms
EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rlat1, rlon1, rlat2, rlon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_KM * c


def distance_km(n1: Node, n2: Node) -> float:
    # Use surface distance as approximation; could adjust with altitude
    return haversine_km(n1.lat, n1.lon, n2.lat, n2.lon)


def fspl_db(d_km: float, freq_hz: float) -> float:
    if d_km <= 0:
        d_km = 0.001
    return 20 * math.log10(d_km) + 20 * math.log10(freq_hz) - 147.55


def snr_linear(fspl_db_val: float, p_tx_dbm: float, noise_dbm: float) -> float:
    rx_dbm = p_tx_dbm - fspl_db_val
    snr_db = rx_dbm - noise_dbm
    return max(10 ** (snr_db / 10), 1e-6)


def capacity_mbps(bw_hz: float, snr_lin: float) -> float:
    return (bw_hz * math.log2(1 + snr_lin)) / 1e6


def latency_ms(distance_km_val: float, proc_queue_ms: float) -> float:
    prop = distance_km_val / (C_KM_PER_MS)  # km / (km/ms) = ms
    return prop + proc_queue_ms


def energy_j(duration_ms: float, p_tx_dbm: float, kind_src: str) -> float:
    # Simplified: power in dBm -> mW; duration ms -> s
    mw = 10 ** (p_tx_dbm / 10)
    w = mw / 1000.0
    coeff = 1.0
    if kind_src == "sat":
        coeff = 1.5
    elif kind_src == "air":
        coeff = 1.2
    return w * (duration_ms / 1000.0) * coeff


def reliability(distance_km_val: float, kind_pair: Tuple[str, str]) -> float:
    base = 1.0
    if "sat" in kind_pair:
        base = 0.9
    if distance_km_val > 0:
        base *= max(0.1, 1.0 - (distance_km_val / 5000.0))
    return min(max(base, 0.0), 1.0)


def elevation_ok(src: Node, dst: Node, elevation_min_deg: float) -> bool:
    # Simplified: accept if either is sat and elevation angle above horizon ~ assume ok beyond threshold distance
    # For now, we allow all sat links; controller can refine later. Keep a basic gate.
    if src.kind == "sat" or dst.kind == "sat":
        return True
    return True
