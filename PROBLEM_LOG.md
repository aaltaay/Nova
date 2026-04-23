# Problem log (agent-maintained)

This file is a **shared memory** of errors fixed and problems identified in this repo. Agents should **search here first** (repo search or open this file) when symptoms look familiar.

## How agents update this file

1. **When:** After you fix a failing build, test, linter error, runtime error, or incorrect behavior; or after you identify a non-obvious root cause worth remembering.
2. **Where:** Prepend a new `##` section **immediately below** the `<!-- ENTRIES_START -->` marker (newest entries at the top).
3. **Keep it short:** A few lines per field is enough.

Entry template (copy and fill in):

```markdown
## YYYY-MM-DD — Short descriptive title

- **Symptom:** What failed or misbehaved (error text, stack trace one-liner, or user-visible behavior).
- **Cause:** Root cause in plain language.
- **Fix:** What changed (conceptually; file paths if helpful).
- **Keywords:** comma, separated, terms, for, search
```

<!-- ENTRIES_START -->

## 2026-04-23 — GitHub Actions “Backend tests” exit 5 with no tests

- **Symptom:** `CI / Deploy` failed on **Backend tests** with “Process completed with exit code 5”; **Frontend build** passed; **Deploy to Railway** skipped.
- **Cause:** `pytest` exits **5** when no tests are collected. The workflow intended to treat 5 as success, but GitHub’s `bash` runs with **`set -e`**, so the shell exited as soon as `pytest` returned 5—before `PYTEST_EXIT=$?` and the `if` ran.
- **Fix:** Run pytest under `set +e`, capture `$?`, then `set -e` and branch on 5 vs other codes.
- **Keywords:** GitHub Actions, pytest, exit code 5, set -e, errexit, no tests collected

## 2026-04-23 — Railway “Wait for CI” skipped frontend; GitHub Actions failed

- **Symptom:** Frontend deployments **SKIPPED** with “CI check suite failed”; backend kept updating; latest UI commits never went live.
- **Cause:** `frontend/scripts/check-railway-api-base.mjs` treated **any** environment with `RAILWAY_PROJECT_ID` as a Railway build. That variable is sometimes copied into **GitHub Actions** repo/org variables; GitHub runners are not Railway, and `VITE_API_BASE_URL` is often unset there → `prebuild` exited 1 → `frontend-build` job failed.
- **Fix:** Require `RAILWAY_PROJECT_ID && !GITHUB_ACTIONS` for the strict check; add a bash default `VITE_API_BASE_URL` in `.github/workflows/deploy.yml` for the build step.
- **Keywords:** Wait for CI, GitHub Actions, RAILWAY_PROJECT_ID, prebuild, frontend-build, skipped

## 2026-04-23 — HOD Momo tab still invisible after tab-bar `overflow-x: auto`

- **Symptom:** Production showed only Gappers / Movers / After Hours / Catalysts; **HOD Momo** never appeared even after adding horizontal scroll on `.tab-bar`.
- **Cause:** `.tab-spacer { flex: 1 }` sat between the tab buttons and “updated … ago” in the **same** flex row. The spacer kept absorbing free space in a way that blocked a proper `min-width: 0` scroll region, so the fifth tab stayed clipped.
- **Fix:** Wrap only the tab `<button>`s in `.tab-bar-scroll` (`flex: 1; min-width: 0; overflow-x: auto`); keep the scan-age as a sibling with `flex-shrink: 0`; remove `.tab-spacer`.
- **Keywords:** HOD Momo, tab bar, flex, overflow, tab-spacer, clipped

## 2026-04-23 — Railway frontend “unreachable” while `/config.json` returned 200

- **Symptom:** Backend healthy; frontend still disconnected; fetching `/config.json` on the frontend host returned HTTP 200 but HTML, not JSON.
- **Cause:** Static hosting SPA fallback served `index.html` for unknown paths when `config.json` was absent from `dist` (postbuild skipped or file not deployed). Bootstrap treated the failed JSON path as failure and fell back to `http://localhost:8000`.
- **Fix:** Inject `<meta name="nova-api-base">` at Vite build from `process.env.VITE_API_BASE_URL`; read meta first in `resolveApiBase`. Validate `/config.json` bodies look like JSON before parsing.
- **Keywords:** Railway, static, SPA fallback, config.json, VITE_API_BASE_URL, localhost, CORS

## 2026-04-23 — `/api/health` stuck at `{"status":"loading",...}` on Railway

- **Symptom:** Hitting the deployed `/api/health` always returned `loading` with `latency_ms: 0`; UI appeared broken; browser console empty for that symptom.
- **Cause:** `_cached_health` defaults to `loading` and is only updated by `_ping_health()` (Alpaca `/v2/account`). Lifespan called `_ping_health` only when `_alpaca_headers()` was non-`None`. With **no** `APCA_API_KEY_ID` / `APCA_API_SECRET_KEY` in the Railway Backend environment, the ping never ran and scans returned early without updating health.
- **Fix:** If credentials are missing at startup, set `_cached_health` to `error` with a clear message and `logger.warning(...)`.
- **Keywords:** health, loading, APCA_API_KEY_ID, APCA_API_SECRET_KEY, Railway, Alpaca, lifespan

## 2026-04-23 — Production UI “backend unreachable” (follow-up: Vite inlining missing)

- **Symptom:** After setting `VITE_API_BASE_URL` on Railway, the hosted UI still showed “Backend unreachable”; the production JS bundle still referenced `http://localhost:8000` only.
- **Cause:** Some Railway frontend builds did not substitute `import.meta.env.VITE_API_BASE_URL` into the emitted chunks even when the variable existed in the dashboard (stale asset hash `index-B-3w0dfo.js` unchanged), so the browser never called the real backend URL.
- **Fix:** Emit `dist/config.json` in `postbuild` from `VITE_API_BASE_URL` / `NOVA_API_BASE`, and resolve the API base in `main.tsx` before loading `App` (fetch `/config.json` when Vite did not inline). `constants.ts` prefers `window.__NOVA_API_BASE__` from that bootstrap.
- **Keywords:** Railway, Vite, VITE_API_BASE_URL, config.json, runtime bootstrap, backend unreachable, localhost

## 2026-04-23 — Production UI “backend unreachable” while Railway backend is healthy

- **Symptom:** Hosted frontend on Railway stayed on loading then showed disconnected / “Backend unreachable”; `curl` to the backend `/api/health` and `/api/gappers` returned 200. Downloaded production `assets/index-*.js` still contained `localhost` / `:8000`, not the Railway backend hostname.
- **Cause:** `VITE_*` variables are inlined at **Vite build time**. Setting `VITE_API_BASE_URL` in the Railway dashboard without a **new** frontend build left the old bundle. Optional: GitHub Actions was configured for `main` only while the repo default branch is `master`, so “wait for CI” could block or never align with pushes.
- **Fix:** Documented behavior via a `prebuild` script that exits non-zero on Railway when `VITE_API_BASE_URL` is unset. Extended `.github/workflows/deploy.yml` to `main` and `master` (including the deploy job condition). Operators must **Redeploy** the Frontend service after setting or changing the variable.
- **Keywords:** Railway, Vite, VITE_API_BASE_URL, build time, CORS, backend unreachable, localhost, Wait for CI, master branch

## 2026-04-16 — Railway Railpack “could not determine how to build” on monorepo root

- **Symptom:** Railway build failed with Railpack: `Script start.sh not found`, `Railpack could not determine how to build the app`, and the analyzed tree showed the full repo (`.cursor/`, `backend/`, `frontend/`, etc.) with no Python at the service root.
- **Cause:** Default builder Railpack only inspects the configured build root. With **Root Directory** left at the repo root, there is no `requirements.txt` or `pyproject.toml` at `./` (Python lives under `backend/`). The old `backend/railway.toml` alone is not applied unless the service points “Config as code” at `/backend/railway.toml`, and `builder = "nixpacks"` is ignored when the platform defaults to Railpack.
- **Fix:** Added a **root `railway.toml`** that sets `builder = "DOCKERFILE"` and `dockerfilePath = "Dockerfile"`, plus a **root `Dockerfile`** that `COPY backend/` and runs uvicorn on `$PORT`. Added **`backend/Dockerfile`** and switched **`backend/railway.toml`** to the same Docker builder for deployments where Root Directory is `backend`. Added **`.dockerignore`** to shrink build context.
- **Keywords:** Railway, Railpack, monorepo, Dockerfile, root directory, Nixpacks, build failed, start.sh

## 2026-04-16 — Volume frozen in scanner lists and ticker detail panel despite continuous data loading

- **Symptom:** Volume column in gapper/mover tables never updated while price changed in real time. Ticker detail panel "Volume" field also stuck at the value fetched on initial load. Zero-volume tickers showed `—` instead of `0`.
- **Cause:** (1) `_handle_trade()` only read `S` (symbol) and `p` (price) from the Alpaca trade WS message, discarding `s` (trade size). (2) `_broadcast_trade_update()` payload had no volume field, so ticker-detail WS clients never received updated volume. (3) `fmtVolume()` used `if (!v)` which treats `0` as falsy.
- **Fix:** `_handle_trade` now extracts `size = int(msg.get("s") or 0)` and adds it to the `volume` field of every updated cache entry (gapper, after-hours, gainer, loser). `_apply_trade_to_mover_list` accepts a `size` param and accumulates it. `_handle_trade` returns the new cumulative volume. `_ws_stream_loop` passes that to `_broadcast_trade_update`, which now includes `volume` in its JSON payload. Frontend `TickerTradeUpdate` interface gains `volume: number | null`; the `trade_update` handler updates `daily_bar.volume` and recomputes `rel_volume` accordingly. `fmtVolume` changed to `if (v == null)`. Drift from WS gaps self-heals via the existing periodic `_fetch_snapshots` scan loop.
- **Keywords:** volume, fmtVolume, _handle_trade, _broadcast_trade_update, trade size, real-time, accumulate, daily_bar, TickerTradeUpdate, rel_volume

## 2026-04-16 — Gapper gap % wrong during pre-market (using day-before-yesterday close)

- **Symptom:** Pre-market gapper table showed inflated gap percentages (e.g., BIRD +432% instead of -22%). Stocks with a large yesterday move appeared as massive gappers even if they were gapping DOWN in pre-market. Stock quote panel also showed wrong change % vs previous close.
- **Cause:** Alpaca snapshot `prevDailyBar` semantics differ by session. During pre-market (before 9:30 ET), `dailyBar` = yesterday's completed regular session bar, and `prevDailyBar` = the session before that (two days ago). The code always used `prevDailyBar.c` as "previous close" regardless of session, so during pre-market it computed gap vs the wrong reference (two days ago vs yesterday).
- **Fix:** Added `_pick_prev_close(snap)` helper in `backend/main.py` that inspects `dailyBar.t` (the bar timestamp). If the bar's date in ET is before today, `dailyBar` is yesterday's close and is returned. Otherwise returns `prevDailyBar.c`. Updated `_compute_gappers()` and `_run_focus_scan()` to use this helper. Updated `_fetch_ticker_snapshot()` to expose `prev_close`, `session_close`, `session_prev_close` fields. Frontend `TickerDetailContent` now uses `snap.prev_close` and shows a Webull-style two-line quote (main line = last regular-session close, sub-line = Pre:/After: with extended-hours price and change vs session close) during pre-market/after-hours.
- **Keywords:** gapper, prev close, prevDailyBar, dailyBar, pre-market, gap percent, Alpaca snapshot, bar timestamp, session close, two-line quote, pre-market quote

## 2026-04-15 — Quote side panel flashes empty / “screen disappears” on ticker click

- **Symptom:** Clicking a scanner row to open a quote briefly blanked the side panel or showed “No data found” before the spinner or quote appeared.
- **Cause:** After `selectedSymbol` updates, React renders **once before** the WebSocket `useEffect` runs. In that frame `loading` and `refreshing` were still false and `detail` was null, so the UI matched the **empty-state** branch (`!loading && !refreshing && !detail && selectedSymbol`). Runtime logs (`panel_branch` with `showEmpty: true` then `showSpinner: true`) confirmed the ordering.
- **Fix:** Treat that pre-effect gap as loading: `awaitingPreEffectFrame = selectedSymbol && !detail && !loading && !refreshing && !fetchFailed`, and `showFullSpinner = loading || awaitingPreEffectFrame`. Show “No data found” only when `fetchFailed` is set after a real WS close/error without an `initial` message (not StrictMode cleanup).
- **Keywords:** side panel, ticker click, flash, empty state, useEffect ordering, WebSocket, quote, StrictMode

## 2026-04-15 — After-hours tab: strong ticker missing despite large move (e.g. MAMO)

- **Symptom:** A symbol looked like a clear after-hours mover (large % change, volume) but never appeared on the After Hours list / tab count stayed low; manual Alpaca snapshot showed a large move vs `dailyBar.c`.
- **Cause:** The gap math and 10% threshold were fine. Alpaca’s `/v2/assets/{symbol}` can return **`tradable: false`** for an otherwise active listing (e.g. `overnight_halted` while another mover like AREB stays `tradable: true`). The scanner only requested snapshots for symbols passing **`tradable`** in `_get_tradable_symbols`, so those names were never scanned.
- **Fix:** Added `SCAN_REQUIRE_TRADABLE` (default `True`) and env **`BLAST_SCAN_REQUIRE_TRADABLE`** (`true`/`false`) so operators can include non-tradable active listings when needed; documented in `constants.py`.
- **Keywords:** after hours, MAMO, tradable false, Alpaca assets, scan universe, overnight_halted, BLAST_SCAN_REQUIRE_TRADABLE

## 2026-04-15 — Alpaca WS “connection limit exceeded” (406) and stale live prices

- **Symptom:** Scanner UI did not update second-by-second; backend log showed repeated `Alpaca WS auth failed` with `code: 406`, `msg: 'connection limit exceeded'`. Sometimes two “connecting” lines appeared close together in `blast.log`.
- **Cause:** `uvicorn --reload` without the `watchfiles` package falls back to **StatReload**, which ignores `--reload-exclude`. The rotating log (`backend/logs/blast.log`) and disk cache (`backend/.cache/`) changed frequently; each change restarted the worker. Overlapping processes each tried to open Alpaca’s market-data WebSocket; Alpaca allows **one** concurrent WS per API key, so new workers got 406 until slots cleared. Multiple long-lived terminals could also leave several backends running at once, making the limit worse.
- **Fix:** Add `watchfiles` to `backend/requirements.txt` so reload exclusions apply; pass `--reload-exclude logs --reload-exclude .cache` in `Run Stock Alert.bat`; keep `ALPACA_WS_BACKOFF_CAP` at 60s to avoid hammering reconnects. When debugging, kill **all** `python3.13` / uvicorn workers (not only `py.exe`) and avoid running several API instances in parallel.
- **Keywords:** Alpaca, WebSocket, 406, connection limit exceeded, uvicorn reload, StatReload, watchfiles, reload-exclude, blast.log, .cache, gappers.json, live data, stale

<!-- (New entries go above this comment; keep newest at top.) -->
