# ADR 021 -- Desk self-heal: what heals itself, what stays a human step

**Status:** Accepted · **Date:** 2026-09-22
**Builds on:** [[010-ib-loop-isolation]] · [[013-ibkr-account-vs-port]] · [[018-desk-venue-vs-spend-arming]] · [[020-three-venues-one-feed]]

## Context

On the night of 2026-09-21 the operator's desk showed *"IBKR enabled: Set
IBKR_ENABLED=true in .env and restart the API"* and *"IB Gateway API port is
open, but Nova session is not READY (reason: disabled, state: disconnected)"*
while both `.env` files on the machine carried `IBKR_ENABLED=true`. The process
on `:8000` was `py -3 run_api.py`, started at 00:47 **from an agent worktree**:
a Playwright run's Vite dev server exposes the same `POST /__nova/start-api`
endpoint the desk uses, a spec's auto-heal clicked it after the operator's own
backend had died, and `backend/paths.env_file_path()` resolves `.env` relative
to the repo root of the running code. The worktree has no `.env`, so every
integration reported "not set" and the checklist blamed the operator's
configuration.

Three things were missing, and they are separate:

1. **Nothing owned the operator's backend process.** When it died the UI could
   only offer "Reload backend", and any replacement that answered `/api/health`
   looked "up" -- even one rooted in the wrong checkout with no `.env`.
2. **The checklist could not say which fact failed.** It derived three rows
   from `/api/ibkr/status` and `/api/health`; it had no way to state "this
   process reads `.env` from `<path>`, which does not exist".
3. **Retrying was unbounded or invisible.** The dialer re-dials forever on its
   own clock; a Gateway that needs an IBC login / IBKR Mobile 2FA looked the
   same as one that Nova simply had not attached to yet.

## Decision

### 1. Diagnostics are a checklist of facts, never a verdict

`GET /api/diagnostics` (owner `backend/diagnostics/`) answers a flat list of
rows, each `{id, group, title, state, detail, cause, fix, since, action,
evidence}`. `state` is one of `ok | warn | fail | off | unknown`; `unknown`
always says *why* Nova cannot tell. `evidence` carries the raw facts (paths,
codes, timestamps, counts) the row was judged from, so an operator or an agent
can dispute the judgement. Groups, in order: **process**, **integrations**,
**gateway**, **market data**, **recorder**, **practice**, **frontend**. Every
row states a cause and a fix in plain words. Collectors are pure functions of
their inputs (`diagnostics/collect*.py`); `diagnostics/gather.py` is the one
imperative shell that reads live modules. `GET /api/diagnostics/bundle` renders
the same rows as plain text for copy/paste into an issue.

The checklist UI (the "Trading prerequisites" gate, same opener, same export)
renders these rows grouped, with a state dot, a one-line detail and an
expandable cause / fix / evidence. It polls every 5 s while open. Per-row
actions exist only for actions that exist today (Reconnect Nova to Gateway,
Launch Gateway, Reload backend, Refresh); the UI never offers a button for a
step Nova cannot take. A **Copy diagnostics** button copies the bundle.

The three legacy rows (Nova API, IBKR enabled, IB Gateway) are still computed
on the client, because they must render while `/api/diagnostics` cannot answer
-- the API being down is the first thing the checklist has to say.

### 2. What heals itself

| Failure | Who heals | Bound |
|---------|-----------|-------|
| The dev-server-started API process exits unexpectedly | the Vite dev server that spawned it (`frontend/scripts/nova-api-supervisor.ts`) | backoff 1, 2, 5, 10, 30 s; at most 5 restarts per 10 minutes, then it stops and says so |
| Gateway API port open, Nova session not READY, connect times out (Gateway still authenticating) | the dialer (`ibkr/session_reconnect.py`) with the attach ledger (`ibkr/attach_retry.py`) | never faster than the longer of the attach ledger (1, 2, 5, 10, 30 s) and the existing auth backoff (30-60 s); at most 5 attempts per 10 minutes before it is a human step polled every 30 s; every attempt recorded on `/api/ibkr/status.attach` and the diagnostics row |
| Gateway API port dark, alternate listening | follow-Gateway heal (`ibkr/gateway_heal.py`, unchanged) | ADR 020 rules: paper -> live always, live -> paper only by opt-in |
| Error 1100 with transport up, or a dead / frozen dialer | `ibkr/session_watchdog.py` (unchanged, ADR 010) | one reset per stuck episode |
| Recorder stopped unrequested | `capture/keepalive.py` (unchanged) | `CAPTURE_RESUME_BACKOFF_SEC`, never across a day |

### 3. What stays a human step, and is reported as such

- **IBC login / IBKR Mobile 2FA.** Nova never types credentials and never
  approves a second factor. Once the attach ledger has classified the stall as
  `human_step` (a pending Second Factor prompt, or the attempt cap reached
  while the Gateway keeps authenticating), the dialer polls politely every
  `IBKR_ATTACH_HUMAN_STEP_POLL_SEC` instead of hammering, and the row says
  *"waiting for you"* with the reason.
- **Another Nova API holding clientId 17** (Error 326). Nova refuses to start
  a second process (`api_instance_lock.py`); killing the other one is the
  operator's call.
- **An IBKR paper login beside a live session** (`account_kind_mismatch`),
  **Read-Only API** ticked in the Gateway (Error 321), a missing market-data
  subscription (10089 / 10168 / 354). Nova can only name these.
- **A missing `.env`.** The API starts (so the checklist can be read) but says
  loudly, in the log, on `/api/health.env_file` and in every integration
  chip's detail, that it found no `.env` at its path and that everything is
  therefore off. It never guesses a different file.
- **Starting the operator's API at all.** The dev server refuses to spawn when
  the main repo's `.env` is missing, when `NOVA_START_API_DISABLED=1` (every
  Playwright run sets it), or when a healthy API already answers on `:8000`
  -- it reports the existing owner instead of binding twice. A restart is an
  explicit `?restart=1` from the Reload backend control.

### 4. Process ownership is stated, not inferred

The dev server spawns the API **only from the main repository's `backend/`**
(`git rev-parse --git-common-dir`, never a worktree) and passes
`NOVA_ENV_PATH` explicitly. `GET /__nova/api-status` reports `{owned, pid,
started, restarts, last_exit, cwd, env_path, main_root, gave_up}` plus a live
probe of `:8000`, and the checklist shows it as the **process owner** row. An
API started by `Run Nova.bat` is *reported* (pid, instance id from
`/api/health`) but not owned; the supervisor never kills a process it did not
start unless the operator asks for a restart.

## Consequences

- One more read-only route pair and one more Vite middleware; no new
  persisted state (the attach ledger and the supervisor state are
  process-local and die with their process, on purpose -- a restart is a new
  episode).
- `session_errors` gains a generic last-error stamp (`last_error()`), so the
  gateway row can say "last IB error 10168 at 00:51: not subscribed" without
  log archaeology.
- The old `PrereqItemRow` renderer is replaced by `diagnostics/DiagnosticRow`;
  the legacy row ids and test ids (`trading-prereq-<id>`) are kept so the
  header, the disconnected banner and existing tests keep working.
- Rejected: exiting the API when `.env` is missing. It would have hidden the
  diagnostics page in exactly the situation it exists for, and it would break
  every test client that runs the lifespan under the pytest env pin.
- Rejected: auto-approving or auto-typing the Gateway login. Never.
- Rejected: an unbounded supervisor. A process that dies five times in ten
  minutes has a cause the operator needs to read, not a sixth restart.

## Verification

- `backend/tests/test_diagnostics_collect.py`, `test_diagnostics_routes.py`,
  `test_gateway_heal_attach_retry.py`, `test_health_env_file.py`.
- `frontend/src/diagnostics/*.test.ts(x)`, `frontend/scripts/nova-api-supervisor.test.ts`,
  `frontend/e2e/desk-diagnostics.spec.ts`.

## Amendment -- the checklist UI and the dev-server guard (2026-09-22)

1. **The checklist is the gate's body.** While the API answers, the Trading
   prerequisites panel renders `GET /api/diagnostics` grouped by area: a state
   dot, a one-line detail, and on expand the cause, the fix and the raw
   evidence; a row's action renders only when the desk has a real handler
   (Reconnect, Launch Gateway, Reload backend where the desk can spawn one,
   Refresh). Copy diagnostics puts the plain-text bundle on the clipboard. When
   the API itself is down the derived rows remain, because only they can offer
   Start API.
2. **The dev server never starts an API from a worktree or without `.env`.**
   `POST /__nova/start-api` refuses with the reason when its checkout is a git
   worktree (`.git` is a file) or the checkout has no `.env`; the spawned API
   gets `NOVA_ENV_PATH` explicitly. `GET /__nova/api-status` reports the root,
   worktree flag, `.env` path and the last start attempt. The guard takes
   effect when the dev server next starts.
3. **Supervision is the desk's existing auto-heal, made safe.** The UI already
   re-starts a dead API through the dev server (`BackendStartButton` on API
   down); with the guards above that heal can no longer produce a wrong-rooted
   or env-less API. A separate long-running supervisor is not added.
4. The backend logs an error at startup and `/api/health.integrations.ibkr`
   says `no .env at <path>` when its `.env` is missing, instead of the silent
   "IBKR_ENABLED not set".

