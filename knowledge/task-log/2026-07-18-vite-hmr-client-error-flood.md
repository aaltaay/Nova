# 2026-07-18 — Silence Vite HMR flood in client-error logs

- **Status:** completed
- **Agents:** parent
- **Domain:** observability / frontend-dev
- **Related:** `CHANGELOG.md` §2026-07-18 Silence Vite HMR noise · `PROBLEM_LOG.md` §2026-07-18 Vite HMR client-error flood

## Task

Explain and stop the backend log screaming hundreds of `client_error` WARNINGs about `send was called before connect` / `@vite/client`.

## Goal

Real product browser errors still reach `/api/client-errors`; Vite HMR/overlay noise does not.

## Why it mattered

The flood made it look like the app was crashing while gappers/IBKR routes were healthy. It also buried real warnings.

## What we changed

- Client: `isDevToolingNoise` in `reportClientError.ts` skips Vite stacks/messages before POST.
- Server: `_is_dev_tooling_noise` in `routes/client_errors.py` returns `{ok:true, ignored:true}` without logging.
- Tests for both layers.

## How it works now

Nova’s global `unhandledrejection` handler still runs, but Vite’s internal “send before HMR connect” failures never become WARNING lines. Prefer a single UI origin in dev (`localhost` *or* `127.0.0.1`, not both).

## Why this approach

- Filter at the reporter (stops HTTP storm) + server (defense if an old tab is open).
- Rejected: disabling `CLIENT_ERROR_REPORT_ENABLED` entirely — that would hide real React crashes.
- Rejected: “fix Vite” — the HMR race is environmental; product code was only amplifying it.

## Verification

- `pytest tests/test_client_errors.py` (3 passed)
- `vitest run src/utils/reportClientError.test.ts` (3 passed)

## Follow-ups

Hard-refresh open Vite tabs after pull so the new client filter loads. If HMR still misbehaves, close duplicate `localhost`/`127.0.0.1` tabs and restart Vite once.

## Keywords

vite, HMR, client-errors, send was called before connect, @vite/client, unhandledrejection
