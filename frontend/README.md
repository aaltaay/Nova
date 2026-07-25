# Nova frontend

React + Vite + TypeScript UI for the Nova trading workstation. The app runs in a browser during development or inside Electron for the packaged desktop build.

## Prerequisites

- Node.js 20+
- Python backend running on `http://127.0.0.1:8000` (see root [README.md](../README.md))

## Setup

```bash
npm install
cp ../.env.example ../.env   # from repo root; set Alpaca read-only keys
```

## Development

```bash
# Browser dev server (http://localhost:5173)
npm run dev

# Electron shell with Vite HMR
npm run electron:dev
```

## Tests

From this directory:

```bash
npm test
```

From the repo root (CI path):

```bash
cd frontend && npm ci && npm test
```

## Production build

```bash
npm run build          # static assets → dist/
npm run electron:pack  # Windows installer → release/
```

Packaged desktop builds store keys and cache under `%APPDATA%\Nova\`.

## Project layout

| Path | Purpose |
|------|---------|
| `src/hod_momo/` | HOD Momo scanner UI |
| `src/ibkr/` | IBKR account and gateway panels |
| `src/workspace/` | Multi-panel workspace shell |
| `src/stock_view/` | Symbol-centric stock view |
| `src/execution_latency/` | Execution telemetry widgets |

See root [README.md](../README.md), [AGENTS.md](../AGENTS.md), and [architecture/README.md](../architecture/README.md) for system-wide documentation.
