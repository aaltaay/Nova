# Change log (agent-maintained)

This file is a running narrative of **what changed in this repo and why**, so future agent and human sessions can get oriented in minutes without digging through diffs.

- **Scope:** code behavior, module boundaries, public APIs, constants, tooling, rules, user-visible UI changes.
- **Out of scope:** pure typo fixes, formatting-only edits, local scratch files.

Bug fixes should **also** be logged in `PROBLEM_LOG.md` (symptom / cause / fix). This file answers "what does the codebase do now and why"; `PROBLEM_LOG.md` answers "what went wrong and how was it diagnosed."

## How agents update this file

1. **When:** After completing any task that changes logic, public behavior, a module boundary, constants, config, build, or rules. Skip pure cosmetics.
2. **Where:** Prepend a new `##` section **immediately below** the `<!-- ENTRIES_START -->` marker (newest entries at the top).
3. **Commit together:** The changelog entry ships in the **same commit** as the code it describes. Do not push code without an entry.
4. **Keep it short:** A few lines per field. No secrets, tokens, or personal data.

Entry template (copy and fill in):

```markdown
## YYYY-MM-DD — Short descriptive title

- **What:** 1–2 sentences on what changed (user-visible + internal).
- **Why:** Trigger for the change (user request, bug class, performance, cleanup).
- **Files touched:** Key files only, e.g. `backend/scanner.py`, `frontend/src/App.tsx`.
- **How it works now:** The mental model a future agent needs — the "oh, got it" paragraph.
- **Verified by:** How you confirmed it works (built + ran, test name, manual click path).
- **Follow-ups:** (optional) anything deferred.
- **Related:** (optional) commit SHA, PROBLEM_LOG entry date, issue link.
```

<!-- ENTRIES_START -->

## 2026-04-23 — Tab bar scroll so HOD Momo stays reachable

- **What:** `.tab-bar` now uses horizontal `overflow-x: auto` with `flex-wrap: nowrap`; `.tab` uses `flex-shrink: 0`.
- **Why:** `.main-col` has `overflow: hidden`, so on typical viewports the fifth tab (**HOD Momo**) was clipped with no way to scroll to it — production looked like the feature was missing.
- **Files touched:** `frontend/src/index.css`.

## 2026-04-23 — Inject API base into `index.html` for Railway static hosts

- **What:** `vite.config.ts` adds a `<meta name="nova-api-base" content="…">` at build time from `VITE_API_BASE_URL` / `NOVA_API_BASE` (same `process.env` Railway uses for `vite build`). `main.tsx` reads that meta first. `/config.json` is only trusted when the response looks like JSON (avoids accepting SPA fallback HTML that returned HTTP 200).
- **Why:** On Railway, `/config.json` was missing from the deploy artifact; the static server returned `index.html` with status 200, JSON parse failed, and the app fell back to `localhost` — “Backend unreachable” despite a correct `VITE_API_BASE_URL` variable.
- **Files touched:** `frontend/vite.config.ts`, `frontend/src/main.tsx`.
- **Verified by:** `npm run build` with and without `VITE_API_BASE_URL`; with env set, `dist/index.html` contains the meta tag and `dist/config.json` is written.

## 2026-04-23 — `/api/health` no longer stuck on `loading` without Alpaca keys

- **What:** On startup, if `APCA_API_KEY_ID` / `APCA_API_SECRET_KEY` are missing, the backend now sets cached health to `status: "error"` with an explanatory message and logs a warning, instead of leaving the default `loading` forever (which happened because `_ping_health` was never called).
- **Why:** Railway operators often omit broker keys at first; `/api/health` then looked like a hung request and was confused with “wrong host” or localhost routing.
- **Files touched:** `backend/main.py`.
- **Verified by:** Code path review; local uvicorn would log the warning when env vars are absent.
- **Related:** `PROBLEM_LOG.md` same date.

## 2026-04-23 — API root JSON + F12 API diagnostics

- **What:** FastAPI now serves `GET /` with a small JSON payload pointing to `/api/health` and `/docs` so opening the backend host in a browser is not mistaken for a broken deploy. The frontend logs structured errors on scanner fetch failure (`API_URL`, `API_BASE_URL`, hint to try `/api/health`). Optional verbose traces via `?apiDebug=1` or `localStorage.setItem('novaApiDebug','1')` plus `/config.json` resolution logging in `main.tsx`. Added `frontend/src/debug.ts`.
- **Why:** Operators saw `{"detail":"Not Found"}` at `/` and assumed the backend was down; that response was FastAPI’s default empty root. Separately, debugging “unreachable” needed clearer console and Network-tab guidance.
- **Files touched:** `backend/main.py`, `frontend/src/App.tsx`, `frontend/src/main.tsx`, `frontend/src/debug.ts`.
- **Verified by:** `npm run build` in `frontend/`; local `curl` to `/` after deploy is optional.
- **Related:** Same-day entries on Railway API base.

## 2026-04-23 — Runtime API base via `config.json` and bootstrap

- **What:** `main.tsx` now resolves the backend URL before loading `App`: use inlined `VITE_API_BASE_URL` when present, otherwise `fetch('/config.json')`. A `postbuild` script writes `dist/config.json` from `VITE_API_BASE_URL` or `NOVA_API_BASE` so production can reach the API even when Vite did not bake the variable into the bundle. `constants.ts` reads `window.__NOVA_API_BASE__` set during that bootstrap. HoD MoMo debug fetches use `API_BASE_URL` + `/api` paths instead of a hardcoded localhost.
- **Why:** The deployed Railway bundle still contained only `http://localhost:8000` while the dashboard variable was set—some builds were not inlining `VITE_*` into JS. Serving `config.json` from the same static origin avoids relying on that substitution alone.
- **Files touched:** `frontend/src/main.tsx`, `frontend/src/constants.ts`, `frontend/scripts/write-dist-api-config.mjs`, `frontend/scripts/check-railway-api-base.mjs`, `frontend/package.json`, `frontend/src/hod_momo/HodMomoDebugPanel.tsx`, `frontend/.env.example`.
- **How it works now:** Production: bootstrap loads `/config.json` when needed, sets `window.__NOVA_API_BASE__`, then the app module graph loads. Local `npm run dev` unchanged (no config file). Railway builds still require `VITE_API_BASE_URL` or `NOVA_API_BASE` so `postbuild` can emit `config.json`.
- **Verified by:** `npm run build` without env (no `config.json`); with `VITE_API_BASE_URL=https://stockalert-production.up.railway.app`, `dist/config.json` contains that URL.
- **Related:** Same-day PROBLEM_LOG entry.

## 2026-04-23 — Railway frontend builds must set `VITE_API_BASE_URL`

- **What:** Added `frontend/scripts/check-railway-api-base.mjs` and an npm `prebuild` hook so builds on Railway fail fast if `VITE_API_BASE_URL` is missing (otherwise Vite embeds `http://localhost:8000` and production shows “backend unreachable”). GitHub Actions workflow now runs on `master` as well as `main`, and the Railway deploy job runs on pushes to either branch.
- **Why:** Deployed frontend JS still pointed at localhost because the env var is only read at **build** time; adding it in the dashboard without a **redeploy** left an old bundle. “Wait for CI” on Railway also never saw a passing workflow when the repo only used `master`.
- **Files touched:** `frontend/scripts/check-railway-api-base.mjs`, `frontend/package.json`, `.github/workflows/deploy.yml`.
- **How it works now:** Local `npm run build` is unchanged. On Railway (`RAILWAY_PROJECT_ID` set), `prebuild` requires `VITE_API_BASE_URL` before `vite build`. After setting the variable, trigger a new Frontend deployment so the bundle is rebuilt.
- **Verified by:** `npm run build` in `frontend/` succeeds locally; same with `RAILWAY_PROJECT_ID=1` set and `VITE_API_BASE_URL=https://example.com` the prebuild passes (manual check).
- **Related:** `PROBLEM_LOG.md` same date.

## 2026-04-17 — Add agent-maintained CHANGELOG.md and `change-log` rule

- **What:** Introduced `CHANGELOG.md` at the repo root and a new always-on rule `.cursor/rules/change-log.mdc` that requires agents to prepend a human-readable summary after every non-trivial task. Sits alongside the existing `problem-log.mdc` / `commit-after-tasks.mdc` policies.
- **Why:** Reading raw diffs or `git log` is too slow when re-entering the project. The user wants a single "swipe through and understand" file, especially the *"how it works now"* narrative that commits and bug logs don't capture.
- **Files touched:** `CHANGELOG.md` (new), `.cursor/rules/change-log.mdc` (new).
- **How it works now:** Three agent-maintained docs cover different questions: `CHANGELOG.md` = "what does this codebase do now and why" (newest-first, prepend on every task), `PROBLEM_LOG.md` = "what bug happened and how was it fixed" (newest-first, prepend on resolutions), `.cursor/rules/*.mdc` = persistent policies. Task completion is not done until the changelog entry exists and ships in the same commit as the code.
- **Verified by:** Built and ran the app via `Run Stock Alert.bat` (uvicorn on `:8000`, Vite on `:5173`) — no code paths changed, doc-only change.
- **Follow-ups:** `progress.md` and `findings.md` (Phase-0 leftovers, last touched 2026-04-13) overlap with this file and should probably be archived or deleted in a future task.
- **Related:** Mirrors the newest-first `<!-- ENTRIES_START -->` convention in `PROBLEM_LOG.md`.
