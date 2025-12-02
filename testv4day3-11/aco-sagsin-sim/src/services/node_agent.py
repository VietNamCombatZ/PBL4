from __future__ import annotations

import json
import os
import time
from pathlib import Path

from ..logging_setup import setup_logging
import threading
import socket
import urllib.request
import time as _time
from typing import Any

NODES_PATH = Path("data/generated/nodes.json")


def main() -> None:
    setup_logging()
    idx = int(os.getenv("NODE_INDEX", "0"))
    if not NODES_PATH.exists():
        time.sleep(2)
    if not NODES_PATH.exists():
        print("nodes.json not found; exiting")
        return
    with open(NODES_PATH, "r", encoding="utf-8") as f:
        nodes = json.load(f)
    node: dict[str, Any] | None = None
    if 0 <= idx < len(nodes):
        try:
            node = nodes[idx]
        except Exception:
            node = None
    if not node:
        print(f"Node agent in standby (no assigned node for idx={idx}); exiting")
        return
    nm = node.get('name') or f"{node.get('kind','node')}-{node.get('id','?')}"
    print(f"Node agent started for node id={node.get('id')} kind={node.get('kind')} name={nm}")
    TCP_PORT = int(os.getenv("NODE_TCP_PORT", "9000"))

    # minimal TCP server: accepts a JSON payload and logs/forwards if instructed
    def _tcp_server():
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", TCP_PORT))
        s.listen(16)
        print(f"[node-{node.get('id')}] TCP server listening on :{TCP_PORT}")
        while True:
            try:
                conn, addr = s.accept()
                data = b""
                conn.settimeout(5.0)
                while True:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                try:
                    msg = json.loads(data.decode("utf-8", errors="ignore"))
                except Exception:
                    msg = {}
                # basic fields: sessionId, path, idx, message
                sid = msg.get("sessionId")
                path = msg.get("path") or []
                cur_i = int(msg.get("idx", 0))
                payload = msg.get("message")
                print(f"[node-{node.get('id')}] TCP recv sid={sid} idx={cur_i} msg={bool(payload)}")
                # forward to next hop if any
                nxt_i = cur_i + 1
                if isinstance(path, list) and nxt_i < len(path):
                    next_node_id = int(path[nxt_i])
                    # compose container name on default network
                    host = f"aco-sagsin-sim-node-{next_node_id}"
                    try:
                        fwd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        fwd.settimeout(3.0)
                        fwd.connect((host, TCP_PORT))
                        fwd_payload = json.dumps({"sessionId": sid, "path": path, "idx": nxt_i, "message": payload}).encode("utf-8")
                        fwd.sendall(fwd_payload)
                        fwd.close()
                        print(f"[node-{node.get('id')}] forwarded to {host}")
                    except Exception as e:
                        print(f"[node-{node.get('id')}] forward failed to {host}: {e}")
                conn.close()
            except Exception:
                time.sleep(0.2)
    # simple heartbeat
    # start a background thread to listen for packet events from controller SSE
    def _listen_events():
        url = os.getenv("CONTROLLER_URL", "http://aco-controller:8080/events")
        backoff = 1
        while True:
            try:
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=60) as resp:
                    backoff = 1
                    buffer = ""
                    for raw in resp:
                        try:
                            line = raw.decode("utf-8")
                        except Exception:
                            continue
                        if line.startswith("data:"):
                            # accumulate JSON data after 'data:'
                            data = line[len("data:"):].strip()
                            buffer = data
                            try:
                                obj = json.loads(buffer)
                            except Exception:
                                obj = None
                            if obj and isinstance(obj, dict):
                                # look for packet-progress events with message
                                t = obj.get("type")
                                node_id = obj.get("nodeId")
                                if node and node_id == node.get("id"):
                                    # print status updates
                                    status = obj.get("status")
                                    if obj.get("message") and status == "success":
                                        print(f"[node-{node.get('id')}] Received message: {obj.get('message')}")
                                    else:
                                        print(f"[node-{node.get('id')}] packet event: status={status}")
            except Exception:
                # reconnect with exponential backoff
                _time.sleep(backoff)
                backoff = min(backoff * 2, 30)

    threading.Thread(target=_listen_events, daemon=True).start()
    threading.Thread(target=_tcp_server, daemon=True).start()

    hb = int(os.getenv("HEARTBEAT_SEC", "30"))
    while True:
        print(f"agent idx={idx} alive")
        time.sleep(hb)


if __name__ == "__main__":
    main()
