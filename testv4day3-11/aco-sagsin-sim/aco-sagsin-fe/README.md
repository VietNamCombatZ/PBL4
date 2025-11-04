# aco-sagsin-fe

React + TypeScript + Vite frontend for SAGSIN ACO controller.

## Quick start

1) Copy env
```bash
cp .env.example .env
```
2) Install deps and run dev
```bash
npm i
npm run dev
```

Set `VITE_API_BASE=http://localhost:8080` to point to the FastAPI backend.
Set `VITE_USE_MOCK=1` to use mock SSE/packet.

Routes: /data, /route, /packet.
