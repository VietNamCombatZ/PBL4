from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Any, Optional

import yaml
from dotenv import load_dotenv


def _to_bool(val: str | bool | None, default: bool) -> bool:
    if isinstance(val, bool):
        return val
    if val is None:
        return default
    return str(val).lower() in {"1", "true", "yes", "on"}


@dataclass
class AcoParams:
    ants: int
    iters: int
    alpha: float
    beta: float
    rho: float
    xi: float
    q0: float
    tau0: float
    mmas: bool
    tau_min: float
    tau_max: float
    weights: list[float]


@dataclass
class LinkModelParams:
    freq_hz: float
    bw_hz: float
    p_tx_dbm: float
    noise_dbm: float
    proc_queue_ms: float


@dataclass
class Config:
    epoch_sec: int
    enable_sea: bool
    enable_ground: bool
    enable_sat: bool
    enable_air: bool
    enable_clustering: bool
    cluster_radius_km: float
    bbox: dict[str, float]
    max_range_km: dict[str, float]
    elevation_min_deg: float
    aco: AcoParams
    link_model: LinkModelParams
    offline: bool
    cache_ttl_sec: int
    http_timeout_sec: int
    http_retries: int
    backoff_factor: float
    # optional selection controls
    continent: Optional[str] = None  # e.g., asia, europe, africa, america, north_america, south_america, oceania
    node_limit: int = 0  # 0 = unlimited
    type_mix: Dict[str, float] | None = None  # e.g., {"sat":0.3, "air":0.5, "ground":0.2, "sea":0.0}


def load_config(path: str = "config.yaml") -> Config:
    load_dotenv(override=True)
    with open(path, "r", encoding="utf-8") as f:
        y: Dict[str, Any] = yaml.safe_load(f)

    aco = y.get("aco", {})
    lm = y.get("link_model", {})

    sel = y.get("selection", {})

    config = Config(
        epoch_sec=int(os.getenv("EPOCH_SEC", y.get("epoch_sec", 10))),
        enable_sea=_to_bool(os.getenv("ENABLE_SEA"), y.get("enable_sea", False)),
        enable_ground=_to_bool(os.getenv("ENABLE_GROUND"), y.get("enable_ground", True)),
        enable_sat=_to_bool(os.getenv("ENABLE_SAT"), y.get("enable_sat", True)),
        enable_air=_to_bool(os.getenv("ENABLE_AIR"), y.get("enable_air", True)),
        enable_clustering=_to_bool(os.getenv("ENABLE_CLUSTERING"), y.get("enable_clustering", True)),
        cluster_radius_km=float(os.getenv("CLUSTER_RADIUS_KM", y.get("cluster_radius_km", 20))),
        bbox={
            "min_lat": float(os.getenv("BBOX_MIN_LAT", y.get("bbox", {}).get("min_lat", -90))),
            "max_lat": float(os.getenv("BBOX_MAX_LAT", y.get("bbox", {}).get("max_lat", 90))),
            "min_lon": float(os.getenv("BBOX_MIN_LON", y.get("bbox", {}).get("min_lon", -180))),
            "max_lon": float(os.getenv("BBOX_MAX_LON", y.get("bbox", {}).get("max_lon", 180))),
        },
        max_range_km=y.get("max_range_km", {}),
        elevation_min_deg=float(os.getenv("ELEVATION_MIN_DEG", y.get("elevation_min_deg", 10))),
        aco=AcoParams(
            ants=int(os.getenv("ANTS", aco.get("ants", 30))),
            iters=int(os.getenv("ITERS", aco.get("iters", 60))),
            alpha=float(os.getenv("ALPHA", aco.get("alpha", 1.0))),
            beta=float(os.getenv("BETA", aco.get("beta", 3.0))),
            rho=float(os.getenv("RHO", aco.get("rho", 0.2))),
            xi=float(os.getenv("XI", aco.get("xi", 0.1))),
            q0=float(os.getenv("Q0", aco.get("q0", 0.2))),
            tau0=float(os.getenv("TAU0", aco.get("tau0", 0.2))),
            mmas=_to_bool(os.getenv("MMAS"), aco.get("mmas", True)),
            tau_min=float(os.getenv("TAU_MIN", aco.get("tau_min", 0.01))),
            tau_max=float(os.getenv("TAU_MAX", aco.get("tau_max", 2.0))),
            weights=[float(x) for x in os.getenv("WEIGHTS", None).split(",")]
            if os.getenv("WEIGHTS")
            else aco.get("weights", [0.5, 0.2, 0.2, 0.1]),
        ),
        link_model=LinkModelParams(
            freq_hz=float(os.getenv("FREQ_HZ", lm.get("freq_hz", 2.4e9))),
            bw_hz=float(os.getenv("BW_HZ", lm.get("bw_hz", 20e6))),
            p_tx_dbm=float(os.getenv("P_TX_DBM", lm.get("p_tx_dbm", 20))),
            noise_dbm=float(os.getenv("NOISE_DBM", lm.get("noise_dbm", -100))),
            proc_queue_ms=float(os.getenv("PROC_QUEUE_MS", lm.get("proc_queue_ms", 2))),
        ),
        offline=_to_bool(os.getenv("OFFLINE"), False),
        cache_ttl_sec=int(os.getenv("CACHE_TTL_SEC", 86400)),
        http_timeout_sec=int(os.getenv("HTTP_TIMEOUT_SEC", 10)),
        http_retries=int(os.getenv("HTTP_RETRIES", 3)),
        backoff_factor=float(os.getenv("BACKOFF_FACTOR", 0.6)),
    continent=(os.getenv("CONTINENT") or sel.get("continent")),
    node_limit=int(os.getenv("NODE_LIMIT", sel.get("node_limit", 0) or 0)),
    type_mix=sel.get("type_mix"),
    )

    return config
