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

Installer output: `frontend/release/Nova-Setup-vNNN.exe` (public identity is the commit-count tag).

Every pull request must pack this EXE in CI (`Desktop pack` workflow). Download it from the workflow artifacts on the PR. Do not merge if that job is red.

### Versioning (commit-count `vNNN`)

Nova's public revision is **`vNNN`**: `v` plus the git commit count from the first commit, at least three digits (`v001`, `v473`, `v1000`). `git rev-list --count HEAD` is the number.

- **SSOT:** repo root `VERSION` stores `vNNN`. `frontend/package.json` stores `0.1.N` because electron-builder requires semver. Both share the same N.
- **CI pack:** `.github/workflows/desktop-pack.yml` checks out the full history, runs `tools/bump_version.py --sync`, packs the Windows NSIS installer, and uploads `Nova-Setup-vNNN.exe`.
- **Releases:** a successful push to `master` / `main` creates git tag `vNNN` only. No GitHub Release object.
- **Install hooks once:** `powershell -File tools/install_git_hooks.ps1` (sets `core.hooksPath` to `.githooks`).
- **pre-commit:** bumps to the next count and stages `VERSION` + `package.json`.
- **pre-push:** blocks push if those files drift from the commit count.
- **Manual sync:** `py -3 tools/bump_version.py --sync` (align to current HEAD without committing).

The packaged app stores Alpaca keys and cache under `%APPDATA%\Nova\` (`.env`, `cache\`, `logs\`).

### First-time setup

- In `frontend/`, run `npm install` if you have not already.
- Ensure Python can run the backend (`py -3` or `python` on PATH) for browser/dev mode.
- Copy `.env.example` → `.env`. IB Gateway is required for scanner/prices. Alpaca keys (`APCA_API_KEY_ID`, `APCA_API_SECRET_KEY`) are for news/listing metadata.

### Deploy

- **Backend:** local only -- no cloud host right now. Use `Run Nova.bat`, Desktop, or uvicorn on `127.0.0.1:8000`.
- **Public site:** `nova.altaystudio.com` is the static marketing page in `site/` (Vercel Root Directory = `site`). It lists features, shows desk screenshots, and links to [Nova-public](https://github.com/aaltaay/Nova-public). It does not run the scanner.
- **App UI:** local only -- Vite at `http://localhost:5173` or the Desktop installer.
- **Desktop:** Electron + local API sidecar -- not a cloud backend.
