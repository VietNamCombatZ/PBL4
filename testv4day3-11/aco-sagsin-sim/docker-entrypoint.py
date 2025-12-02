#!/usr/bin/env python3
"""
Entrypoint that assigns a unique NODE_INDEX to container instances when not provided.

Behavior:
- If the environment variable NODE_INDEX is already set (non-empty), do nothing and exec the given command.
- Otherwise, use a host-mounted directory (default: /var/lib/aco/node_assignments) to store a simple counter file.
- Acquire an exclusive lock on a lock file and increment the counter to obtain a unique index.
- Export NODE_INDEX in the environment and exec the requested command.

This approach works when `docker-compose` starts multiple replicas and a shared bind mount is configured
so all replicas can coordinate assignments. It avoids using the Docker API or privileged sockets.
"""
import fcntl
import os
import sys
from pathlib import Path
import json
import socket as pysocket
from typing import Optional, List

ASSIGN_DIR = Path(os.environ.get("NODE_ASSIGN_DIR", "/var/lib/aco/node_assignments"))
COUNTER_FILE = ASSIGN_DIR / "counter.txt"
LOCK_FILE = ASSIGN_DIR / "counter.lock"


def ensure_assign_dir():
    try:
        ASSIGN_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        # fallback: try /tmp
        tmp = Path("/tmp/node_assignments")
        tmp.mkdir(parents=True, exist_ok=True)
        return tmp
    return ASSIGN_DIR


def allocate_index(assign_dir: Path) -> int:
    lock_path = assign_dir / "counter.lock"
    counter_path = assign_dir / "counter.txt"

    # open lock file and acquire exclusive lock
    with open(lock_path, "a+") as lf:
        try:
            fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        except Exception:
            pass
        # read current counter
        if counter_path.exists():
            try:
                with open(counter_path, "r+") as cf:
                    txt = cf.read().strip()
                    val = int(txt) if txt else 0
                    val += 1
                    cf.seek(0)
                    cf.truncate(0)
                    cf.write(str(val))
                    cf.flush()
                    return val
            except Exception:
                # if anything goes wrong, fallback to creating/resetting
                with open(counter_path, "w") as cf:
                    cf.write("1")
                return 1
        else:
            try:
                with open(counter_path, "w") as cf:
                    cf.write("1")
                return 1
            except Exception:
                return 1


def derive_from_docker_socket() -> Optional[int]:
    """Attempt to derive the replica number via Docker Engine API.

    Requires mounting the Docker socket read-only into the container:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    """
    sock_path = os.environ.get("DOCKER_SOCK", "/var/run/docker.sock")
    if not os.path.exists(sock_path):
        return None
    try:
        cid = os.environ.get("HOSTNAME") or pysocket.gethostname()
        # Basic HTTP over UNIX domain socket
        s = pysocket.socket(pysocket.AF_UNIX, pysocket.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect(sock_path)
        req = f"GET /containers/{cid}/json HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n"
        s.sendall(req.encode("ascii"))
        chunks = []
        while True:
            data = s.recv(8192)
            if not data:
                break
            chunks.append(data)
        s.close()
        resp = b"".join(chunks).decode("utf-8", errors="ignore")
        # Split headers/body
        sep = "\r\n\r\n"
        if sep not in resp:
            return None
        headers, body = resp.split(sep, 1)
        # Response can be chunked; handle simple non-chunked first
        if "Transfer-Encoding: chunked" in headers:
            # naive dechunker sufficient for small JSON
            out = []
            rest = body
            while True:
                line, _, rest = rest.partition("\r\n")
                try:
                    n = int(line.strip(), 16)
                except Exception:
                    break
                if n == 0:
                    break
                chunk = rest[:n]
                out.append(chunk)
                rest = rest[n+2:]
            body = "".join(out)
        data = json.loads(body)
        # Prefer compose container-number label
        labels = (data.get("Config", {}).get("Labels", {})) or {}
        num = labels.get("com.docker.compose.container-number")
        if num and str(num).isdigit():
            return int(num)
        # Fallback to name suffix
        name = data.get("Name") or ""
        import re
        m = re.search(r"-(\d+)$", name)
        if m:
            return int(m.group(1))
    except Exception:
        return None
    return None


def main():
    # If NODE_INDEX is explicitly provided, just exec
    node_env = os.environ.get("NODE_INDEX")
    if node_env and node_env.strip():
        # Exec the provided command
        if len(sys.argv) > 1:
            os.execvp(sys.argv[1], sys.argv[1:])
        else:
            # nothing to run
            print("No command provided to entrypoint; exiting.")
            sys.exit(0)

    # Try to derive index from multiple hints (in order):
    # - /etc/hosts content (may include service-name aliases)
    # - socket FQDN
    # - reverse DNS of primary container IP
    derived_idx = None
    candidates: List[str] = []
    try:
        import re
        import socket

        # 1) /etc/hosts
        try:
            with open("/etc/hosts", "r", encoding="utf-8") as hf:
                content = hf.read()
            candidates.append(content)
        except Exception:
            pass

        # 2) socket FQDN / hostname
        try:
            candidates.append(socket.gethostname())
        except Exception:
            pass
        try:
            candidates.append(socket.getfqdn())
        except Exception:
            pass

        # 3) reverse DNS of container IPs
        try:
            # gather non-loopback IPv4s
            addrs = set()
            try:
                infos = socket.getaddrinfo(socket.gethostname(), None)
                for fam, _, _, _, sa in infos:
                    if fam == socket.AF_INET:
                        ip = sa[0]
                        if not ip.startswith("127."):
                            addrs.add(ip)
            except Exception:
                pass
            # also try environment-provided HOSTNAME -> IP
            try:
                ip = socket.gethostbyname(socket.gethostname())
                if not ip.startswith("127."):
                    addrs.add(ip)
            except Exception:
                pass
            for ip in addrs:
                try:
                    rev = socket.gethostbyaddr(ip)
                    # rev[0] primary name, rev[1] aliases
                    candidates.append(" ".join([rev[0], *rev[1]]))
                except Exception:
                    continue
        except Exception:
            pass

        # Search all candidates for 'node-<n>' or 'node_<n>'
        blob = "\n".join([c for c in candidates if c])
        m = re.search(r"(?:\b|_)(?:node)[-_](\d+)(?:\b)", blob)
        if m:
            derived_idx = int(m.group(1))
        # 4) Docker engine (if socket mounted)
        if derived_idx is None:
            docker_num = derive_from_docker_socket()
            if docker_num is not None:
                derived_idx = docker_num
    except Exception:
        derived_idx = None

    # Strict mode: require derived index and never fall back to counter
    force_strict = os.environ.get("FORCE_DERIVED_INDEX", "").lower() in {"1","true","yes","on"}
    if force_strict and derived_idx is None:
        # emit a short diagnostic teaser to help users understand what was inspected
        sample = " | ".join([s for s in candidates if s][:2]) if 'candidates' in locals() else ""
        print("FORCE_DERIVED_INDEX enabled but could not derive index from container name or DNS; exiting.")
        if sample:
            print("Hints inspected (truncated):", sample[:200])
        sys.exit(1)

    # Assign index using shared directory (fallback when not derived)
    assign_dir = ensure_assign_dir()
    try:
        idx = derived_idx if derived_idx is not None else allocate_index(assign_dir)
        os.environ["NODE_INDEX"] = str(idx)
        if derived_idx is not None:
            print(f"Assigned NODE_INDEX={idx} (derived from container name)")
        else:
            print(f"Assigned NODE_INDEX={idx} (from {assign_dir})")
    except Exception as e:
        print("Failed to allocate NODE_INDEX, defaulting to 0:", e)
        os.environ["NODE_INDEX"] = "0"

    # Exec the provided command
    if len(sys.argv) > 1:
        os.execvp(sys.argv[1], sys.argv[1:])
    else:
        print("No command provided to entrypoint; exiting.")
        sys.exit(0)


if __name__ == "__main__":
    main()
