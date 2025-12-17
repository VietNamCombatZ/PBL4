from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
import math
from typing import Optional
import uuid
import queue

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import logging

from ..aco.solver import ACO
from ..config import Config, load_config
from ..logging_setup import setup_logging
from ..net.graph import build_graph
from ..net.updater import rebuild_from_nodes, update_epoch
from ..types import GraphState, Link, Node
from ..lib import metrics as metrics_lib

app = FastAPI(title="ACO SAGSIN Controller")

# CORS for local dev frontend (Vite @ :5173) and same-origin callers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to ["http://localhost:5173", "http://127.0.0.1:5173"] if needed
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATE_LOCK = threading.Lock()
STATE: Optional[GraphState] = None
CFG: Optional[Config] = None
NODES_PATH = Path("data/generated/nodes.json")
SPEED_MULTIPLIER: float = 1.0

# In-memory SSE broadcaster for packet progress events
SUBSCRIBERS: list[queue.Queue[str]] = []
SUB_LOCK = threading.Lock()

def _subscribe() -> queue.Queue[str]:
    q: queue.Queue[str] = queue.Queue()
    with SUB_LOCK:
        SUBSCRIBERS.append(q)
    return q

def _unsubscribe(q: queue.Queue[str]) -> None:
    with SUB_LOCK:
        if q in SUBSCRIBERS:
            SUBSCRIBERS.remove(q)

def _broadcast(evt: dict) -> None:
    # include explicit SSE event name when available and JSON data
    event_name = evt.get("type", "message")
    payload = json.dumps(evt)
    frame = f"event: {event_name}\n" + f"data: {payload}\n\n"
    with SUB_LOCK:
        subs = list(SUBSCRIBERS)
    for q in subs:
        try:
            q.put_nowait(frame)
        except Exception:
            pass


def _bfs_path(gs: GraphState, src: int, dst: int) -> list[int]:
    """Unweighted shortest-path fallback using enabled edges only.
    Returns a list of node ids from src to dst if reachable, else [].
    """
    from collections import deque
    if src == dst:
        return [src]
    visited = {int(src)}
    prev: dict[int, Optional[int]] = {int(src): None}
    dq = deque([int(src)])
    while dq:
        u = dq.popleft()
        for v in gs.adj.get(u, []):
            idx = gs.edge_index.get((u, v))
            if idx is None or not gs.links[idx].enabled:
                continue
            if v in visited:
                continue
            visited.add(v)
            prev[v] = u
            if v == dst:
                # reconstruct
                path: list[int] = []
                cur = v
                while cur is not None:
                    path.append(cur)
                    cur = prev.get(cur)
                path.reverse()
                return path
            dq.append(v)
    return []


class RouteReq(BaseModel):
    src: int
    dst: int
    objective: Optional[dict] = None


class ToggleReq(BaseModel):
    u: int
    v: int
    enabled: bool


class SendPacketReq(BaseModel):
    src: int
    dst: int
    protocol: str = "UDP"
    message: Optional[str] = None
    path: Optional[list[int]] = None  # optional precomputed path for TCP relay


@app.get("/")
def root():
    return {
        "service": "aco-sagsin-controller",
        "docs": "/docs",
        "endpoints": [
            "/nodes",
            "/links",
            "/route",
            "/simulate/toggle-link",
            "/simulate/set-epoch",
            "/simulate/send-packet",
            "/events",
            "/config/reload",
            "/health",
            "/health/db",
            "/tcp/test",
        ],
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/health/db")
def health_db():
    try:
        if not CFG or not CFG.enable_db:
            return {"enable_db": False, "available": False}
        from ..data.db import available as _db_available

        avail = _db_available()
        return {"enable_db": True, "available": bool(avail)}
    except Exception:
        return {"enable_db": bool(CFG.enable_db) if CFG else False, "available": False}


@app.on_event("startup")
def on_start() -> None:
    setup_logging()
    global CFG, STATE
    CFG = load_config()
    log = logging.getLogger(__name__)
    nodes_source_path = str(NODES_PATH)
    use_db_nodes = False
    # Attempt DB nodes first when enabled
    try:
        if CFG.enable_db:
            from ..data.db import read_nodes as _read_nodes, available as _db_available
            if _db_available():
                db_nodes = _read_nodes()
                if db_nodes:
                    # Write to temp file for rebuild convenience
                    NODES_PATH.parent.mkdir(parents=True, exist_ok=True)
                    with open(NODES_PATH, "w", encoding="utf-8") as f:
                        json.dump(db_nodes, f)
                    use_db_nodes = True
    except Exception:
        pass
    if not use_db_nodes and not NODES_PATH.exists():
        # fallback toy nodes if neither DB nor file nodes are present
        toy = [
            Node(id=0, kind="ground", lat=0.0, lon=0.0, alt_m=0.0, name="ground-0").__dict__,
            Node(id=1, kind="ground", lat=0.1, lon=0.1, alt_m=0.0, name="ground-1").__dict__,
            Node(id=2, kind="sat", lat=0.2, lon=0.2, alt_m=550000.0, name="sat-2").__dict__,
        ]
        NODES_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(NODES_PATH, "w", encoding="utf-8") as f:
            json.dump(toy, f)
    if use_db_nodes:
        log.info("Loaded nodes from MongoDB (written to %s)", NODES_PATH)
    elif NODES_PATH.exists():
        log.info("Loaded nodes from file %s", NODES_PATH)
    else:
        log.info("Loaded toy nodes (fallback)")
    STATE = rebuild_from_nodes(nodes_source_path)

    # start epoch thread
    th = threading.Thread(target=_epoch_loop, daemon=True)
    th.start()


def _epoch_loop() -> None:
    global STATE, CFG
    while True:
        time.sleep(CFG.epoch_sec if CFG else 10)
        with STATE_LOCK:
            if STATE is not None:
                STATE = update_epoch(STATE)


@app.get("/nodes")
def get_nodes():
    with STATE_LOCK:
        if not STATE:
            return []
        out = []
        for n in STATE.nodes:
            d = dict(n.__dict__)
            if not d.get("name"):
                d["name"] = f"{n.kind}-{n.id}"
            out.append(d)
        return out


@app.get("/links")
def get_links():
    with STATE_LOCK:
        if not STATE:
            return []
        return [l.__dict__ for l in STATE.links]


@app.get("/nodes/positions")
def nodes_positions():
    """Return dynamic positions for moving kinds (sat, air, sea) with simple drift.
    Longitudes drift over time; latitudes apply small jitter for air/sea.
    """
    import math
    now = time.time()
    with STATE_LOCK:
        if not STATE:
            return []
        # movement parameters (can later be driven by config.yaml)
        kinds_move = {"sat", "air", "sea"}
        deg_per_sec = {"sat": 0.15, "air": 0.02, "sea": 0.005}
        jitter_km = {"air": 1.0, "sea": 0.2, "sat": 0.0}
        out = []
        for n in STATE.nodes:
            lat = float(n.lat)
            lon = float(n.lon)
            if n.kind in kinds_move:
                dps = float(deg_per_sec.get(n.kind, 0.0))
                # drift longitude, wrap [-180,180]
                lon = ((lon + dps * now * SPEED_MULTIPLIER + 180.0) % 360.0) - 180.0
                jk = float(jitter_km.get(n.kind, 0.0))
                if jk > 0:
                    # ~1 deg ~ 111km
                    lat = max(-90.0, min(90.0, lat + (math.sin((now * SPEED_MULTIPLIER) / 17.0 + n.id) * jk) / 111.0))
            out.append({"id": int(n.id), "lat": lat, "lon": lon, "alt_km": float(n.alt_m) / 1000.0})
        return out


@app.get("/simulate/get-speed")
def get_speed():
    return {"multiplier": SPEED_MULTIPLIER}


class SpeedReq(BaseModel):
    multiplier: float


@app.post("/simulate/set-speed")
def set_speed(req: SpeedReq):
    global SPEED_MULTIPLIER
    try:
        m = float(req.multiplier)
        if m <= 0:
            raise ValueError("multiplier must be > 0")
        SPEED_MULTIPLIER = m
        return {"ok": True, "multiplier": SPEED_MULTIPLIER}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/route")
def post_route(req: RouteReq):
    with STATE_LOCK:
        if not STATE:
            raise HTTPException(500, "Graph not ready")
        weights = None
        if req.objective and "weights" in req.objective:
            w = req.objective["weights"]
            if isinstance(w, list) and len(w) == 4:
                weights = (float(w[0]), float(w[1]), float(w[2]), float(w[3]))
        aco = ACO(STATE, weights_override=weights)
        path, cost = aco.solve(req.src, req.dst)
        try:
            import logging

            logging.getLogger(__name__).info("route result: path=%s cost=%s", path, cost)
        except Exception:
            pass
        # Guard against NaN/Infinity to keep JSON RFC-compliant and signal infeasible routes
        if not path or not math.isfinite(cost):
            # Fallback to BFS on enabled edges for reachability
            path = _bfs_path(STATE, int(req.src), int(req.dst))
            if not path:
                raise HTTPException(status_code=422, detail="No feasible path found for the given src/dst")
            # approximate cost as sum of per-edge objective from ACO costs when available
            try:
                from ..aco.objective import compute_edge_costs
                costs = compute_edge_costs(STATE, weights)
                acc = 0.0
                for i in range(len(path) - 1):
                    acc += float(costs.get((path[i], path[i+1]), 1.0))
                cost = acc
            except Exception:
                cost = float('nan')
        # compute server-side metrics for apples-to-apples comparison
        try:
            latency_ms = metrics_lib.path_latency_ms_for_state(path, STATE.nodes)
            throughput_mbps = metrics_lib.path_throughput_mbps_for_state(path, STATE.nodes)
        except Exception:
            latency_ms = None
            throughput_mbps = None
        return {"path": path, "cost": float(cost), "latency_ms": latency_ms, "throughput_mbps": throughput_mbps}


@app.post("/simulate/toggle-link")
def post_toggle(req: ToggleReq):
    with STATE_LOCK:
        if not STATE:
            raise HTTPException(500, "Graph not ready")
        idx = STATE.edge_index.get((req.u, req.v))
        if idx is None:
            raise HTTPException(404, "link not found")
        STATE.links[idx].enabled = req.enabled
        return {"ok": True}


@app.post("/simulate/set-epoch")
def post_epoch():
    global STATE
    with STATE_LOCK:
        if not STATE:
            raise HTTPException(500, "Graph not ready")
        STATE = update_epoch(STATE)
        return {"ok": True}


@app.post("/config/reload")
def post_reload():
    global CFG, STATE
    CFG = load_config()
    with STATE_LOCK:
        # Try DB again on reload if enabled
        db_used = False
        try:
            if CFG.enable_db:
                from ..data.db import read_nodes as _read_nodes, available as _db_available
                if _db_available():
                    db_nodes = _read_nodes()
                    if db_nodes:
                        with open(NODES_PATH, "w", encoding="utf-8") as f:
                            json.dump(db_nodes, f)
                        db_used = True
        except Exception:
            pass
        STATE = rebuild_from_nodes(str(NODES_PATH))
    try:
        log = logging.getLogger(__name__)
        if db_used:
            log.info("Reloaded nodes from MongoDB")
        else:
            log.info("Reloaded nodes from file %s", NODES_PATH)
    except Exception:
        pass
    return {"ok": True}


@app.post("/simulate/send-packet")
def post_send_packet(req: SendPacketReq):
    with STATE_LOCK:
        if not STATE:
            raise HTTPException(500, "Graph not ready")
        # allow client-provided path (e.g., FE sends known path) else compute via ACO
        if req.path and len(req.path) >= 2:
            path = [int(x) for x in req.path]
            cost = 0.0
        else:
            aco = ACO(STATE)
            path, cost = aco.solve(req.src, req.dst)
        # capture links and edge_index snapshot for simulation thread to compute latencies
        links_snapshot = list(STATE.links)
        edge_index_snapshot = dict(STATE.edge_index)
    if not path or (not math.isfinite(cost) and not req.path):
        # Try BFS fallback to keep UX stable when ACO misses a reachable path
        with STATE_LOCK:
            path = _bfs_path(STATE, int(req.src), int(req.dst))
        if not path:
            raise HTTPException(status_code=422, detail="No feasible path found for the given src/dst")
        cost = 0.0

    session_id = str(uuid.uuid4())
    # precompute ACO metrics to return to the caller
    try:
        computed_latency_ms = metrics_lib.path_latency_ms_for_state(path, STATE.nodes)
        computed_throughput_mbps = metrics_lib.path_throughput_mbps_for_state(path, STATE.nodes)
    except Exception:
        computed_latency_ms = None
        computed_throughput_mbps = None

    def _simulate():
        # compute cumulative latency per node along the path (ms)
        cumulative = 0.0
        # helper to read latency between u->v
        def _link_latency(u: int, v: int) -> float:
            idx = edge_index_snapshot.get((u, v))
            if idx is None:
                # try reverse (graph may be undirected)
                idx = edge_index_snapshot.get((v, u))
            if idx is None:
                return 0.0
            try:
                return float(links_snapshot[idx].latency_ms)
            except Exception:
                return 0.0
        for i, node_id in enumerate(path):
            # cumulative latency up to this node (sum of latencies of links before this node)
            if i == 0:
                cumulative = 0.0
            else:
                u = path[i - 1]
                v = path[i]
                cumulative += _link_latency(u, v)

            try:
                # include optional message when provided; useful at destination
                base_evt = {
                    "sessionId": session_id,
                    "nodeId": node_id,
                    "cumulativeLatencyMs": cumulative,
                }
                # pending
                pending_evt = {"type": "packet-progress", "status": "pending", **base_evt}
                if req.message:
                    pending_evt["message"] = req.message if i == 0 else None
                _broadcast(pending_evt)
                time.sleep(0.3)
                # success
                success_evt = {"type": "packet-progress", "status": "success", **base_evt}
                # attach message to success event only at destination node
                if req.message and node_id == req.dst:
                    success_evt["message"] = req.message
                _broadcast(success_evt)
            except Exception:
                pass
            time.sleep(0.2)

    # Start TCP relay across containers (real traffic), while SSE keeps UI updated
    def _tcp_relay():
        try:
            import socket
            TCP_PORT = int(os.environ.get("NODE_TCP_PORT", "9000"))
            # open connection to first node in path
            if len(path) >= 2:
                first = int(path[0])
                host = f"aco-sagsin-sim-node-{first}"
                try:
                    print(f"[tcp] connect first hop host={host} port={TCP_PORT}")
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(3.0)
                    s.connect((host, TCP_PORT))
                    payload = json.dumps({"sessionId": session_id, "path": path, "idx": 0, "message": req.message}).encode("utf-8")
                    s.sendall(payload)
                    s.close()
                    print(f"[tcp] sent payload to {host}")
                    # emit start event
                    _broadcast({"type":"packet-progress","status":"pending","sessionId":session_id,"nodeId":first,"cumulativeLatencyMs":0.0,"message": req.message})
                except Exception as e:
                    print(f"[tcp] first hop connect failed to {host}:{TCP_PORT} err={e}")
        except Exception:
            pass

    threading.Thread(target=_simulate, daemon=True).start()
    threading.Thread(target=_tcp_relay, daemon=True).start()
    return {"sessionId": session_id, "path": path, "cost": float(cost) if math.isfinite(cost) else None, "latency_ms": computed_latency_ms, "throughput_mbps": computed_throughput_mbps}


@app.get("/events")
def get_events():
    q = _subscribe()

    def _gen():
        try:
            yield ":ok\n\n"
            while True:
                try:
                    msg = q.get(timeout=15)
                    yield msg
                except Exception:
                    yield ":keepalive\n\n"
        finally:
            _unsubscribe(q)

    return StreamingResponse(_gen(), media_type="text/event-stream")


@app.get("/tcp/test")
def tcp_test(node_id: int, port: int = 9000):
    """Connectivity check: try to open a TCP connection to a node container by id.
    Returns success or error details to help diagnose DNS/network issues.
    """
    host = f"aco-sagsin-sim-node-{int(node_id)}"
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect((host, int(port)))
        s.close()
        return {"ok": True, "host": host, "port": int(port)}
    except Exception as e:
        return {"ok": False, "host": host, "port": int(port), "error": str(e)}
