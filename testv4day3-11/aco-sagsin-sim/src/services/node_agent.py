from __future__ import annotations

import json
import os
import time
from pathlib import Path

from ..logging_setup import setup_logging

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
    else:
        print("Node agent in standby (no assigned node)")
    # simple heartbeat
    while True:
        print(f"agent idx={idx} alive")
        time.sleep(30)


if __name__ == "__main__":
    main()
