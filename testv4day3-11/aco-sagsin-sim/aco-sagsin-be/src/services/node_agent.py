from __future__ import annotations

import json
import os
import time
from pathlib import Path

from ..logging_setup import setup_logging
import threading
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
    if idx < len(nodes):
        node = nodes[idx]
    nm = node.get('name') or f"{node.get('kind','node')}-{node.get('id','?')}"
    print(f"Node agent started for node id={node['id']} kind={node['kind']} name={nm}")
    # else:
    #     print("Node agent in standby (no assigned node)")
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
                                if node_id == node.get("id"):
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

    th = threading.Thread(target=_listen_events, daemon=True)
    th.start()

    while True:
        print(f"agent idx={idx} alive")
        time.sleep(30)


if __name__ == "__main__":
    main()
