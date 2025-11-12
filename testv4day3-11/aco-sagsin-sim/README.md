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
NODES=60 make up
```

Start (detached, direct Docker Compose alternative):

```bash
# build and run detached, scaling node service
# docker compose up -d --build --scale node=10
# docker compose up -d --build controller
docker compose up -d  controller
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

Selection (optional):
- `selection.continent`: one of asia, europe, africa, north_america, south_america, america, oceania.
- `selection.node_limit`: max nodes to keep (0 = unlimited).
- `selection.type_mix`: percentage mix per kind, e.g. `{sat: 0.3, air: 0.5, ground: 0.2, sea: 0.0}`.

Notes:
- Selection is applied after bbox and clustering.
- When `type_mix` is provided with `node_limit`, quotas are computed from the mix and filled greedily; any remainder is backfilled from remaining nodes.

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
  - POST /simulate/send-packet {src,dst,protocol}
  - GET /events (SSE stream for packet-progress)
  - POST /config/reload

- node agent: one per container, binds NODE_INDEX to a node from nodes.json and heartbeats.

## Notes

- Data is cached under `data/cache` with TTL.
- If offline, seed uses cache and falls back to a tiny synthetic toy graph if cache is empty, so /route still works.
- The ACO objective normalizes latency, inverse-capacity, energy, inverse-reliability to [0,1] with weights.

## Packet simulation

- Start a packet and observe events:

- Observe event:
```bash
curl -s -X POST http://localhost:8080/simulate/send-packet \
  -H 'content-type: application/json' \
  -d '{"src":0,"dst":1,"protocol":"UDP"}' | jq .
```

- Start send a packet
```bash
curl -s -N http://localhost:8080/events &
curl -s -X POST http://localhost:8080/simulate/send-packet \
  -H 'content-type: application/json' \
  -d '{"src":1,"dst":25,"protocol":"UDP"}' | jq .
```

- From inside the image (or via docker exec), you can use a small CLI:

```bash
docker compose run --rm controller python -m src.tools.send_packet_cli --src 1 --dst 25 --protocol UDP
```
