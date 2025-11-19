from __future__ import annotations

from typing import Dict, List, Tuple

from ..config import load_config
from ..types import GraphState, Node, Link
from .link_models import (
    capacity_mbps,
    distance_km,
    elevation_ok,
    energy_j,
    fspl_db,
    latency_ms,
    reliability,
    snr_linear,
)


def _max_range(kind_u: str, kind_v: str, cfg) -> float:
    key = None
    pair = {kind_u, kind_v}
    if pair == {"air", "air"}:
        key = "air_air"
    elif pair == {"ground", "ground"}:
        key = "ground_ground"
    elif pair == {"ground", "air"}:
        key = "ground_air"
    elif pair == {"ground", "sat"}:
        key = "ground_sat"
    elif pair == {"air", "sat"}:
        key = "air_sat"
    elif pair == {"sat", "sat"}:
        key = "sat_sat"
    return float(cfg.max_range_km.get(key, 500))


def build_graph(nodes: List[Node]) -> GraphState:
    cfg = load_config()
    links: List[Link] = []

    for i, u in enumerate(nodes):
        for j, v in enumerate(nodes):
            if j <= i:
                continue
            d = distance_km(u, v)
            if d > _max_range(u.kind, v.kind, cfg):
                continue
            if not elevation_ok(u, v, cfg.elevation_min_deg):
                continue

            lm = cfg.link_model
            fspl = fspl_db(d, lm.freq_hz)
            snr = snr_linear(fspl, lm.p_tx_dbm, lm.noise_dbm)
            cap = capacity_mbps(lm.bw_hz, snr)
            lat = latency_ms(d, lm.proc_queue_ms)
            ene = energy_j(lat, lm.p_tx_dbm, u.kind)
            rel = reliability(d, (u.kind, v.kind))

            links.append(
                Link(
                    u=u.id,
                    v=v.id,
                    latency_ms=lat,
                    capacity_mbps=cap,
                    energy_j=ene,
                    reliability=rel,
                    enabled=True,
                )
            )

    adj: Dict[int, List[int]] = {n.id: [] for n in nodes}
    edge_index: Dict[Tuple[int, int], int] = {}
    for idx, e in enumerate(links):
        adj[e.u].append(e.v)
        adj[e.v].append(e.u)
        edge_index[(e.u, e.v)] = idx
        edge_index[(e.v, e.u)] = idx

    return GraphState(nodes=nodes, links=links, adj=adj, edge_index=edge_index)
