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
        ],
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.on_event("startup")
def on_start() -> None:
    setup_logging()
    global CFG, STATE
    CFG = load_config()
    if not NODES_PATH.exists():
        # fallback toy nodes
        toy = [
            Node(id=0, kind="ground", lat=0.0, lon=0.0, alt_m=0.0, name="ground-0").__dict__,
            Node(id=1, kind="ground", lat=0.1, lon=0.1, alt_m=0.0, name="ground-1").__dict__,
            Node(id=2, kind="sat", lat=0.2, lon=0.2, alt_m=550000.0, name="sat-2").__dict__,
        ]
        NODES_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(NODES_PATH, "w", encoding="utf-8") as f:
            json.dump(toy, f)
    STATE = rebuild_from_nodes(str(NODES_PATH))

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
            raise HTTPException(status_code=422, detail="No feasible path found for the given src/dst")
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
        STATE = rebuild_from_nodes(str(NODES_PATH))
    return {"ok": True}


@app.post("/simulate/send-packet")
def post_send_packet(req: SendPacketReq):
    with STATE_LOCK:
        if not STATE:
            raise HTTPException(500, "Graph not ready")
        aco = ACO(STATE)
        path, cost = aco.solve(req.src, req.dst)
        # capture links and edge_index snapshot for simulation thread to compute latencies
        links_snapshot = list(STATE.links)
        edge_index_snapshot = dict(STATE.edge_index)
    if not path or not math.isfinite(cost):
        raise HTTPException(status_code=422, detail="No feasible path found for the given src/dst")

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

    threading.Thread(target=_simulate, daemon=True).start()
    return {"sessionId": session_id, "path": path, "cost": float(cost), "latency_ms": computed_latency_ms, "throughput_mbps": computed_throughput_mbps}


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
