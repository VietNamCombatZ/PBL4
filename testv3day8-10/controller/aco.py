import math, random
from typing import Dict, Tuple, List
# from .models import NodeInfo, NextHopTable
# from .geo import haversine_km, los_possible
from models import NodeInfo, NextHopTable  
from geo import haversine_km, los_possible

def build_graph(nodes: Dict[int, NodeInfo], max_link_km: float) -> Dict[int, List[int]]:
    adj = {nid: [] for nid in nodes}
    ids = list(nodes.keys())
    for i in range(len(ids)):
        for j in range(i+1, len(ids)):
            a = nodes[ids[i]]
            b = nodes[ids[j]]
            if los_possible(a.lat,a.lon,a.alt_km, b.lat,b.lon,b.alt_km) and \
               haversine_km(a.lat,a.lon,b.lat,b.lon) <= max_link_km:
                adj[a.node_id].append(b.node_id)
                adj[b.node_id].append(a.node_id)
    return adj

def aco_next_hop(nodes: Dict[int, NodeInfo], max_link_km: float, iters=10, ants=40) -> NextHopTable:
    """
    Trả về bảng next-hop: (src,dst)->nhảy kế tiếp.
    Heuristic: 1/distance, pheromone trên cạnh.
    """
    adj = build_graph(nodes, max_link_km)
    # Khởi tạo pheromone
    tau = {}  # (u,v) -> pheromone
    for u, nbrs in adj.items():
        for v in nbrs:
            tau[(u,v)] = 1.0

    def choose_next(u, dst):
        nbrs = adj.get(u, [])
        if not nbrs: return None
        # Ưu tiên gần đích + pheromone
        scores = []
        for v in nbrs:
            du = haversine_km(nodes[v].lat,nodes[v].lon, nodes[dst].lat,nodes[dst].lon) + 1e-3
            heur = 1.0/du
            ph = tau[(u,v)]
            scores.append((v, (heur**2) * (ph**1)))
        s = sum(sc for _, sc in scores) or 1.0
        r = random.random()*s
        acc = 0.0
        for v, sc in scores:
            acc += sc
            if acc >= r: return v
        return scores[-1][0]

    # Lặp ACO (rất đơn giản)
    for _ in range(iters):
        # bay kiến giữa các cặp ngẫu nhiên
        for _a in range(ants):
            src, dst = random.sample(list(nodes.keys()), 2)
            u = src
            visited = set([u])
            path = []
            for _step in range(64):
                v = choose_next(u, dst)
                if v is None: break
                path.append((u,v))
                if v == dst: break
                if v in visited: break
                visited.add(v)
                u = v
            # cập nhật pheromone nếu tới đích
            if path and path[-1][1] == dst:
                L = sum(haversine_km(nodes[x].lat,nodes[x].lon, nodes[y].lat,nodes[y].lon) for x,y in path)
                delta = 1.0/(L+1e-6)
                for e in path:
                    tau[e] = tau.get(e,1.0) + delta
        # bay hơi
        for e in list(tau.keys()):
            tau[e] *= 0.9
            if tau[e] < 1e-4: tau[e] = 1e-4

    # Suy ra next-hop tốt nhất theo pheromone
    nexthop = {}
    for src in nodes:
        for dst in nodes:
            if src == dst: continue
            nbrs = adj.get(src, [])
            if not nbrs: continue
            best = max(nbrs, key=lambda v: tau.get((src,v), 0.0))
            nexthop[(src,dst)] = best
    return nexthop
