# aco-sagsin-sim

Ant Colony Optimization (ACO) path selection simulator for SAGSIN (Space–Air–Ground–Sea Integrated Network). Exposes a FastAPI REST/SSE backend, optional MongoDB for data persistence, and a React (Vite) frontend.

## Prerequisites

- macOS with Docker Desktop (Engine running)
- Docker Compose v2
- Node.js 18+ (for the frontend)
- Make (optional convenience)

Recommended Docker Desktop resources:
- CPUs: 4–8
- Memory: 8–16 GB
- Disk image: enough free space

## Project layout

- Backend (FastAPI): aco-sagsin-sim
- Frontend (Vite React): aco-sagsin-fe
- Data cache: data/cache
- Generated nodes: data/generated/nodes.json
- Config: config.yaml
- Compose: docker-compose.yml

## Configuration

Edit `config.yaml` to tune features:
- enable_ground/sat/air/sea: which kinds to include
- elevation_min_deg: 5 (lower for easier links)
- max_range_km: per-kind link range caps
- link_model (recommended to avoid zero throughput):
  - freq_hz: 9.0e8
  - bw_hz: 10e6
  - p_tx_dbm: 30
  - noise_dbm: -95

After changing config, reload the controller:
```bash
curl -s -X POST http://localhost:8080/config/reload | jq .
```

## Environment (MongoDB)

MongoDB is optional; when enabled, fetched caches and generated nodes are saved to DB (and still written to files).

Controller env (compose defaults can be added):
- ENABLE_DB=true
- MONGO_URI=mongodb://mongo:27017
- MONGO_DB=aco
- MONGO_CACHE_COLLECTION=cache
- MONGO_NODES_COLLECTION=nodes

## Build and run (backend + Mongo)

```bash
# from aco-sagsin-sim
docker compose build --no-cache
docker compose up -d mongo controller

# verify health
curl -s http://localhost:8080/health | jq .
curl -s http://localhost:8080/health/db | jq .
```

Seed data (nodes) if you have a seeder target:
```bash
make seed
curl -s -X POST http://localhost:8080/config/reload | jq .
```

Inspect DB contents:
```bash
docker compose exec -T mongo mongosh --quiet --eval 'db.getSiblingDB("aco").getCollectionInfos().map(c=>c.name)'
docker compose exec -T mongo mongosh --quiet --eval 'var d=db.getSiblingDB("aco").nodes.findOne({_id:"nodes"}); d ? d.payload.length : 0'
```

## Run the frontend

```bash
cd aco-sagsin-fe
cp .env.example .env
# set VITE_API_BASE=http://localhost:8080 in .env
npm i
npm run dev
# open http://localhost:5173 (default Vite port)
```

Routes:
- /data — nodes and links
- /route — find routes (ACO/RWR), latency/throughput
- /packet — send packet (simulated; SSE progress)

## Scaling node containers (strict mapping)

Strict mode matches `NODE_INDEX` to the container suffix (node-25 → 25). This avoids index drift.

Recommended: scale in waves with low parallelism to keep Docker Desktop stable.

```bash
# strict index mapping
FORCE_DERIVED_INDEX=true

# start infra
docker compose up -d mongo controller

# scale nodes safely (batches + low parallelism)
COMPOSE_PARALLEL_LIMIT=3 docker compose create --scale node=50
COMPOSE_PARALLEL_LIMIT=3 docker compose create --scale node=100
COMPOSE_PARALLEL_LIMIT=3 docker compose create --scale node=150
COMPOSE_PARALLEL_LIMIT=3 docker compose create --scale node=200
```

If you patched the image, force-recreate nodes:
```bash
docker compose build --no-cache
FORCE_DERIVED_INDEX=true COMPOSE_PARALLEL_LIMIT=3 \
  docker compose up -d --force-recreate --no-deps --scale node=200 node
```

Service vs container names:
- Compose service name: `node` (use with `docker compose logs node`)
- Container name: `aco-sagsin-sim-node-26` (use with `docker logs aco-sagsin-sim-node-26`)

## Movement and speed controls (optional)

If motion endpoints are enabled:
- `/nodes/positions` — returns drifting positions for dynamic kinds (sat/air/sea)
- `/simulate/set-speed` — set multiplier (1, 10, 100)
- Frontend pages have per-page speed and pause/play; switching pages resets positions and speed to 1x.

Start polling on Route/Packet/Data pages via the FE (already wired).

## Packet simulation

Trigger a packet (path computed on server; SSE streams progress to FE):
```bash
curl -sS -X POST http://localhost:8080/simulate/send-packet \
  -H 'Content-Type: application/json' \
  -d '{"src":4,"dst":117,"protocol":"TCP","message":"hello from host"}' | jq
```

If throughput shows 0.00 Mbps in FE, enable adaptive formatting or tune `config.yaml` link model as above.

## Troubleshooting

- “Cannot connect to the Docker daemon … docker.sock”
  - Restart Docker Desktop (macOS):
    ```bash
    osascript -e 'quit app "Docker"'; open -a Docker
    ```
  - Reduce parallelism and scale in waves:
    ```bash
    COMPOSE_PARALLEL_LIMIT=2 docker compose up -d --scale node=50
    ```
  - Check context:
    ```bash
    docker context ls; docker context use default; docker info
    ```

- Controller healthy but UI not reachable
  - Confirm port binding:
    ```bash
    docker inspect -f '{{ .NetworkSettings.Ports }}' aco-controller
    curl -sS http://localhost:8080/health
    ```

- Logs for a single replica
  - Service (all replicas):
    ```bash
    docker compose logs -f node
    ```
  - Specific container:
    ```bash
    docker logs -f aco-sagsin-sim-node-26
    ```

- Strict derivation failures
  - If a node exits with:
    `FORCE_DERIVED_INDEX enabled but could not derive index; exiting`
  - Recreate nodes or relax strict mode:
    ```bash
    FORCE_DERIVED_INDEX=false COMPOSE_PARALLEL_LIMIT=3 docker compose up -d --no-recreate --scale node=200 node
    ```

## Useful API

```bash
curl -s http://localhost:8080/health | jq .
curl -s http://localhost:8080/nodes | jq 'length'
curl -s http://localhost:8080/links | jq '.[0:5]'
curl -s -X POST http://localhost:8080/route -H 'Content-Type: application/json' -d '{"src":11,"dst":108}' | jq .
```

## Clean up

```bash
docker compose down
# remove exited node replicas (if needed)
docker rm -f $(docker ps -aq --filter "name=aco-sagsin-sim-node" --filter "status=exited") 2>/dev/null || true
```