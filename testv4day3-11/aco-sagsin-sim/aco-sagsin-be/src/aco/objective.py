from __future__ import annotations

from typing import Dict, Tuple

from ..types import GraphState


def normalize(value: float, min_v: float, max_v: float) -> float:
    if max_v <= min_v:
        return 0.0
    x = (value - min_v) / (max_v - min_v)
    return min(max(x, 0.0), 1.0)


def compute_edge_costs(gs: GraphState, weights_override: Tuple[float, float, float, float] | None = None) -> Dict[Tuple[int, int], float]:
    # precompute min/max for normalization
    lats = [e.latency_ms for e in gs.links if e.enabled]
    caps = [e.capacity_mbps for e in gs.links if e.enabled]
    enes = [e.energy_j for e in gs.links if e.enabled]
    rels = [e.reliability for e in gs.links if e.enabled]

    if not lats:
        lats = [0.0]
    if not caps:
        caps = [1.0]
    if not enes:
        enes = [0.0]
    if not rels:
        rels = [1.0]

    min_lat, max_lat = min(lats), max(lats)
    min_cap, max_cap = min(caps), max(caps)
    min_ene, max_ene = min(enes), max(enes)
    min_rel, max_rel = min(rels), max(rels)

    from ..config import load_config

    weights = list(weights_override) if weights_override else load_config().aco.weights
    a, b, c, d = weights

    costs: Dict[Tuple[int, int], float] = {}
    for e in gs.links:
        if not e.enabled:
            continue
        lat_n = normalize(e.latency_ms, min_lat, max_lat)
        inv_cap_n = normalize((1.0 / max(e.capacity_mbps, 1e-6)), (1.0 / max_cap), (1.0 / max(min_cap, 1e-6)))
        ene_n = normalize(e.energy_j, min_ene, max_ene)
        inv_rel_n = normalize((1.0 - e.reliability), (1.0 - max_rel), (1.0 - min_rel))
        cost = a * lat_n + b * inv_cap_n + c * ene_n + d * inv_rel_n + 1e-6
        costs[(e.u, e.v)] = cost
        costs[(e.v, e.u)] = cost
    return costs
