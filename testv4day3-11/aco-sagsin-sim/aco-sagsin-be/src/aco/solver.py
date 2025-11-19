from __future__ import annotations

import math
import random
from typing import Dict, List, Tuple

from ..config import load_config
from ..types import GraphState
from .objective import compute_edge_costs


class ACO:
    def __init__(self, gs: GraphState, weights_override: tuple[float, float, float, float] | None = None):
        self.gs = gs
        self.cfg = load_config().aco
        self.costs = compute_edge_costs(gs, weights_override)
        self.tau: Dict[Tuple[int, int], float] = {}
        for (u, v), c in self.costs.items():
            self.tau[(u, v)] = self.cfg.tau0

    def _eta(self, u: int, v: int) -> float:
        # heuristic desirability = 1/cost
        return 1.0 / max(self.costs[(u, v)], 1e-9)

    def _neighbors(self, u: int) -> List[int]:
        return [v for v in self.gs.adj.get(u, []) if (u, v) in self.costs and self._edge_enabled(u, v)]

    def _edge_enabled(self, u: int, v: int) -> bool:
        idx = self.gs.edge_index.get((u, v))
        return idx is not None and self.gs.links[idx].enabled

    def solve(self, src: int, dst: int) -> Tuple[List[int], float]:
        best_path: List[int] = []
        best_cost = float("inf")
        ants, iters = self.cfg.ants, self.cfg.iters
        alpha, beta = self.cfg.alpha, self.cfg.beta
        rho, xi, q0 = self.cfg.rho, self.cfg.xi, self.cfg.q0
        mmas = self.cfg.mmas
        tau_min, tau_max = self.cfg.tau_min, self.cfg.tau_max

        for _ in range(iters):
            for _a in range(ants):
                path = [src]
                visited = {src}
                cost_acc = 0.0
                cur = src
                while cur != dst:
                    nbrs = [v for v in self._neighbors(cur) if v not in visited]
                    if not nbrs:
                        # dead end
                        cost_acc = float("inf")
                        path = []
                        break
                    # select next
                    if random.random() < q0:
                        # exploitation
                        v = max(
                            nbrs,
                            key=lambda x: (self.tau[(cur, x)] ** alpha) * (self._eta(cur, x) ** beta),
                        )
                    else:
                        # probabilistic selection
                        scores = [
                            (self.tau[(cur, v)] ** alpha) * (self._eta(cur, v) ** beta) for v in nbrs
                        ]
                        ssum = sum(scores)
                        if ssum <= 0:
                            v = random.choice(nbrs)
                        else:
                            r = random.random()
                            acc = 0.0
                            v = nbrs[-1]
                            for vv, sc in zip(nbrs, scores):
                                acc += sc / ssum
                                if r <= acc:
                                    v = vv
                                    break
                    # local update
                    self.tau[(cur, v)] = (1 - xi) * self.tau[(cur, v)] + xi * self.cfg.tau0
                    # accumulate cost
                    cost_acc += self.costs[(cur, v)]
                    path.append(v)
                    visited.add(v)
                    cur = v

                if path and cost_acc < best_cost:
                    best_cost = cost_acc
                    best_path = path[:]

            # global update (reinforcement on best path)
            if best_path:
                delta = 1.0 / max(best_cost, 1e-9)
                for i in range(len(best_path) - 1):
                    u, v = best_path[i], best_path[i + 1]
                    self.tau[(u, v)] = (1 - rho) * self.tau[(u, v)] + rho * delta
                    self.tau[(v, u)] = (1 - rho) * self.tau[(v, u)] + rho * delta

            if mmas:
                for k in list(self.tau.keys()):
                    self.tau[k] = min(max(self.tau[k], tau_min), tau_max)

        return best_path, best_cost
