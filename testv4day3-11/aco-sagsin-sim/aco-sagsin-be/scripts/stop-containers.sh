#!/usr/bin/env bash
# Stop containers for this Docker Compose project (fallback: stop all running containers)
# Usage: ./scripts/stop-containers.sh

set -eu

# Determine repo root (one level up from this script)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR/.."

cd "$REPO_ROOT"

# If a compose file exists in the repo root, prefer using `docker compose stop`
if [ -f docker-compose.yml ] || [ -f docker-compose.yaml ] || [ -f docker-compose.yaml ]; then
  echo "Found compose file in $REPO_ROOT — stopping this project's containers (docker compose stop)."
  docker compose stop
  echo "Stopped compose-managed containers."
  exit 0
fi

# Fallback: stop all running containers (global behaviour)
CONTAINERS=$(docker ps -q || true)
if [ -z "$CONTAINERS" ]; then
  echo "No running containers to stop."
  exit 0
fi

echo "Stopping all running containers (fallback):"
docker ps --format "table {{.ID}}\t{{.Names}}\t{{.Status}}"
docker stop $CONTAINERS
echo "Stopped containers." 
