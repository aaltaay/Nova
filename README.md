# Nova

Stock alert automation system (read-only market data; does not execute trades).

## Open the app (Windows)

1. Open the project folder `Nova`.
2. **Double-click** `Run Nova.bat`.

You should get:

- **API:** [http://127.0.0.1:8000](http://127.0.0.1:8000)
- **Web UI:** [http://localhost:5173](http://localhost:5173) (the script tries to open this in your browser)

Two separate command windows run the API and the UI. Close a window to stop that part of the stack.

### First-time setup

- In `frontend/`, run `npm install` if you have not already.
- Ensure Python can run the backend (the batch file uses `py -3` or falls back to `python`).
- Copy `.env` with Alpaca keys (`APCA_API_KEY_ID`, `APCA_API_SECRET_KEY`, etc.) if missing.

### Command line (same as the batch file)

From the repo root:

```bat
Run Nova.bat
```

Or start each part yourself: in `backend/`, `py -3 -m uvicorn main:app --reload --host 127.0.0.1 --port 8000`; in `frontend/`, `npm run dev`.

### Deploy

- **Frontend:** Vercel project `nova` (Git push / Vercel Git integration).
- **Backend:** Railway (see `.github/workflows/deploy.yml`).
