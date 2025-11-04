# aco-sagsin-sim

Ant Colony Optimization (ACO) path selection simulator for SAGSIN (Space–Air–Ground–Sea Integrated Network).

Run locally with Docker Compose and interact via a REST API.

## Quick start

Prerequisites: Docker Desktop (daemon running), Docker Compose, make.

1) Copy env and config

```
cp .env.example .env
```

2) Seed data (fetch with cache, clustering, bbox as configured). If offline and no cache, a small synthetic graph is generated so the API still works:

```
make seed
```

3) Launch controller and node agents:

```
make up
```

4) Query route (example src=1, dst=25):

```
curl -s -X POST localhost:8080/route \
  -H "Content-Type: application/json" \
  -d '{"src":1,"dst":25}' | jq .
```

5) Inspect nodes/links:

```
curl -s localhost:8080/nodes | jq . | head
curl -s localhost:8080/links | jq . | head
```

6) Toggle a link or advance an epoch:

```
curl -s -X POST localhost:8080/simulate/toggle-link -H 'Content-Type: application/json' -d '{"u":1,"v":2,"enabled":false}'
curl -s -X POST localhost:8080/simulate/set-epoch
```

7) Reload config.yaml at runtime:
```
curl -s -X POST localhost:8080/config/reload
```

## Start and Stop the app

Start (foreground, uses Makefile):

```bash
# default scales node agents from NODES (defaults to 50 in Makefile)
make up

# scale to a specific number of node agents
NODES=10 make up
```

Start (detached, direct Docker Compose alternative):

```bash
# build and run detached, scaling node service
docker compose up -d --build --scale node=10
```

Stop the stack (keep volumes/cache):

```bash
docker compose down
```

Stop the stack and remove volumes (reset generated/cache data):

```bash
# Makefile convenience
make down

# or with docker compose directly
docker compose down -v
```

## Configuration

- `.env` controls environment variables, e.g. offline mode and epoch duration.
- `config.yaml` controls data sources, clustering, link model params, ACO params, ranges, elevation, etc.

Key flags:
- enable_sea/ground/sat/air: turn sources on/off
- enable_clustering, cluster_radius_km
- bbox filter
- epoch_sec controls dynamic updates
- offline uses cache when network unavailable

## Development

Formatting/linting: ruff, black, mypy.

Tests:

```
pytest -q
```

## Services

- controller: FastAPI on :8080
  - GET /nodes
  - GET /links
  - POST /route {src,dst,objective?}
  - POST /simulate/toggle-link
  - POST /simulate/set-epoch
  - POST /config/reload

- node agent: one per container, binds NODE_INDEX to a node from nodes.json and heartbeats.

## Notes

- Data is cached under `data/cache` with TTL.
- If offline, seed uses cache and falls back to a tiny synthetic toy graph if cache is empty, so /route still works.
- The ACO objective normalizes latency, inverse-capacity, energy, inverse-reliability to [0,1] with weights.
