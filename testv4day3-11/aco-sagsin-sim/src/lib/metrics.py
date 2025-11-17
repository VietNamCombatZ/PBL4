"""Lightweight metrics helpers ported from aco_formulas.txt

Provide path latency (ms) and throughput (Mbps) computations so the
controller can return the same metrics the frontend computes.
"""
import math
from typing import List, Optional

C_LIGHT_MPS = 299_792_458.0
EARTH_RADIUS_M = 6_371_000.0

def deg2rad(d: float) -> float:
    return d * math.pi / 180.0

def slant_range_m(lat1: float, lon1: float, alt1_m: Optional[float], lat2: float, lon2: float, alt2_m: Optional[float]) -> float:
    a1 = alt1_m or 0.0
    a2 = alt2_m or 0.0
    def to_ecef(lat: float, lon: float, alt: float):
        lat_r = deg2rad(lat)
        lon_r = deg2rad(lon)
        r = EARTH_RADIUS_M + alt
        x = r * math.cos(lat_r) * math.cos(lon_r)
        y = r * math.cos(lat_r) * math.sin(lon_r)
        z = r * math.sin(lat_r)
        return x, y, z
    x1, y1, z1 = to_ecef(lat1, lon1, a1)
    x2, y2, z2 = to_ecef(lat2, lon2, a2)
    dx, dy, dz = x1 - x2, y1 - y2, z1 - z2
    return math.sqrt(dx * dx + dy * dy + dz * dz)

def fspl_db_km_ghz(d_km: float, f_ghz: float) -> float:
    if d_km <= 0 or f_ghz <= 0:
        return 0.0
    return 20.0 * math.log10(d_km) + 20.0 * math.log10(f_ghz) + 92.45

def thermal_noise_dbm(bw_hz: float, noise_figure_db: float = 5.0, t0_dbmhz: float = -174.0) -> float:
    if bw_hz <= 0:
        return -1e9
    return t0_dbmhz + 10.0 * math.log10(bw_hz) + noise_figure_db

def db_to_linear(x_db: float) -> float:
    return 10.0 ** (x_db / 10.0)

def shannon_capacity_bps(bw_hz: float, snr_linear: float) -> float:
    if bw_hz <= 0:
        return 0.0
    return bw_hz * math.log2(1.0 + max(0.0, snr_linear))

def link_throughput_bps_from_budget(d_m: float,
                                     f_ghz: float = 2.4,
                                     bw_hz: float = 1e6,
                                     pt_dbm: float = 30.0,
                                     gt_dbi: float = 0.0,
                                     gr_dbi: float = 0.0,
                                     nf_db: float = 5.0,
                                     phy_eff: float = 0.8,
                                     mac_eff: float = 0.9,
                                     code_rate: float = 0.9) -> float:
    d_km = max(1e-6, d_m / 1000.0)
    fspl = fspl_db_km_ghz(d_km, f_ghz)
    pr_dbm = pt_dbm + gt_dbi + gr_dbi - fspl
    n_dbm = thermal_noise_dbm(bw_hz, nf_db)
    snr_db = pr_dbm - n_dbm
    snr_lin = db_to_linear(snr_db)
    c = shannon_capacity_bps(bw_hz, snr_lin)
    eff = max(0.0, phy_eff) * max(0.0, mac_eff) * max(0.0, code_rate)
    return max(0.0, eff * c)

def transmission_delay_ms(packet_bytes: int, rate_bps: float) -> float:
    bits = packet_bytes * 8
    if rate_bps <= 0:
        return float('inf')
    return (bits / rate_bps) * 1000.0

def propagation_delay_ms(distance_m: float, speed_mps: float = C_LIGHT_MPS) -> float:
    return distance_m / speed_mps * 1000.0

def hop_latency_ms(packet_bytes: int, rate_bps: float, distance_m: float, proc_ms: float = 1.0, queue_ms: float = 0.0) -> float:
    return transmission_delay_ms(packet_bytes, rate_bps) + propagation_delay_ms(distance_m) + max(0.0, proc_ms) + max(0.0, queue_ms)

def path_latency_ms_for_state(path: List[int], nodes: List, packet_bytes: int = 1500,
                              f_ghz: float = 2.4, bw_hz: float = 1e6, pt_dbm: float = 30.0,
                              gt_dbi: float = 0.0, gr_dbi: float = 0.0, nf_db: float = 5.0) -> float:
    if not path or len(path) < 2:
        return 0.0
    total = 0.0
    for i in range(len(path) - 1):
        u_id = path[i]
        v_id = path[i + 1]
        a = next((n for n in nodes if n.id == u_id), None)
        b = next((n for n in nodes if n.id == v_id), None)
        if not a or not b:
            continue
        d = slant_range_m(a.lat, a.lon, getattr(a, 'alt_m', None), b.lat, b.lon, getattr(b, 'alt_m', None))
        link_bps = link_throughput_bps_from_budget(d, f_ghz=f_ghz, bw_hz=bw_hz, pt_dbm=pt_dbm, gt_dbi=gt_dbi, gr_dbi=gr_dbi, nf_db=nf_db)
        total += hop_latency_ms(packet_bytes, max(1.0, link_bps), d)
    return total

def path_throughput_mbps_for_state(path: List[int], nodes: List,
                                   f_ghz: float = 2.4, bw_hz: float = 1e6, pt_dbm: float = 30.0,
                                   gt_dbi: float = 0.0, gr_dbi: float = 0.0, nf_db: float = 5.0) -> float:
    if not path or len(path) < 2:
        return 0.0
    per_link = []
    for i in range(len(path) - 1):
        u_id = path[i]
        v_id = path[i + 1]
        a = next((n for n in nodes if n.id == u_id), None)
        b = next((n for n in nodes if n.id == v_id), None)
        if not a or not b:
            continue
        d = slant_range_m(a.lat, a.lon, getattr(a, 'alt_m', None), b.lat, b.lon, getattr(b, 'alt_m', None))
        cap = link_throughput_bps_from_budget(d, f_ghz=f_ghz, bw_hz=bw_hz, pt_dbm=pt_dbm, gt_dbi=gt_dbi, gr_dbi=gr_dbi, nf_db=nf_db)
        per_link.append(cap)
    if not per_link:
        return 0.0
    path_bps = min(per_link)
    return path_bps / 1e6
