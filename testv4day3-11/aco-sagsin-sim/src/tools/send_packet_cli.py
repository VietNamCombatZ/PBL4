#!/usr/bin/env python3
"""
Simple CLI to trigger packet send via the controller API.
Usage:
  python -m src.tools.send_packet_cli --src 1 --dst 42 --protocol UDP --base http://localhost:8080
This uses only stdlib (urllib) to avoid extra dependencies.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--src", type=int, required=True)
    p.add_argument("--dst", type=int, required=True)
    p.add_argument("--protocol", type=str, default="UDP")
    p.add_argument("--base", type=str, default="http://localhost:8080")
    args = p.parse_args()

    url = args.base.rstrip("/") + "/simulate/send-packet"
    payload = json.dumps({"src": args.src, "dst": args.dst, "protocol": args.protocol}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("content-type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            print(body)
            return 0
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode('utf-8', errors='ignore')}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
