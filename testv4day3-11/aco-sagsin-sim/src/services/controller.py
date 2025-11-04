from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
import math
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ..aco.solver import ACO
from ..config import Config, load_config
from ..logging_setup import setup_logging
from ..net.graph import build_graph
from ..net.updater import rebuild_from_nodes, update_epoch
from ..types import GraphState, Link, Node

app = FastAPI(title="ACO SAGSIN Controller")

STATE_LOCK = threading.Lock()
STATE: Optional[GraphState] = None
CFG: Optional[Config] = None
NODES_PATH = Path("data/generated/nodes.json")


class RouteReq(BaseModel):
    src: int
    dst: int
    objective: Optional[dict] = None


class ToggleReq(BaseModel):
    u: int
    v: int
    enabled: bool


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
        return {"path": path, "cost": float(cost)}


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
