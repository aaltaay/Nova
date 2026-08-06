# Nova

Stock alert automation: IBKR scanner/market data locally, optional gated IBKR orders (paper default), Alpaca for news/listing only. `auto_live` is NO-GO.

## Open the app (Windows)

### Option A — browser (web UI)

1. Open the project folder `Nova`.
2. **Double-click** `Run Nova.bat`.

You should get:

- **API:** [http://127.0.0.1:8000](http://127.0.0.1:8000)
- **Web UI:** [http://localhost:5173](http://localhost:5173)

### Option B — installable desktop (Electron + local API)

Full local stack: Electron shell + FastAPI sidecar on loopback (same React UI).

```bat
cd frontend
npm install
npm run electron:dev
```

Build a Windows installer (NSIS):

```bat
cd frontend
npm run electron:pack
```

Installer output: `frontend/release/Nova-Setup-*.exe`.

The packaged app stores Alpaca keys and cache under `%APPDATA%\Nova\` (`.env`, `cache\`, `logs\`).

### First-time setup

- In `frontend/`, run `npm install` if you have not already.
- Ensure Python can run the backend (`py -3` or `python` on PATH) for browser/dev mode.
- Copy `.env.example` → `.env`. IB Gateway is required for scanner/prices. Alpaca keys (`APCA_API_KEY_ID`, `APCA_API_SECRET_KEY`) are for news/listing metadata.

### Deploy

- **Backend:** local only -- no cloud host right now. Use `Run Nova.bat`, Desktop, or uvicorn on `127.0.0.1:8000`.
- **Frontend (web):** optional Vercel project `nova` (Git push) for the static UI.
- **Desktop:** Electron + local API sidecar -- not a cloud backend.
