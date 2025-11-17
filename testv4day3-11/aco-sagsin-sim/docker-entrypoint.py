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

    # Assign index using shared directory
    assign_dir = ensure_assign_dir()
    try:
        idx = allocate_index(assign_dir)
        os.environ["NODE_INDEX"] = str(idx)
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
