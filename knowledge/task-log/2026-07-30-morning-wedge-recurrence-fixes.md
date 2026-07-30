# 2026-07-30 -- Morning wedge recurrence fixes

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed | ibkr-ops (bootstrap) | maintainer (scripts)
- **Related:** `CHANGELOG.md` §2026-07-30 Morning wedge · `PROBLEM_LOG.md` §Morning empty scanners · OPEN/DEFERRED Premarket bootstrap

## Task

Deep-investigate recurring empty scanners after morning login; ship fixes so the API_WEDGED / stuck-Loading path does not return tomorrow. Defer "must be up before 04:00 ET for gappers / no manual start" as a labeled OPEN issue.

## Goal

Daily bootstrap recycles a wedged API for real; completed-orders no longer floods the event loop; logging cannot stall `/api/health`; OPEN issue documents the premarket-on-time product gap.

## Why it mattered

Two mornings in a row the user woke up to empty tables. IBKR could be connected with 50 gainers in cache while the UI showed Loading / API_WEDGED -- trust-breaking and easy to misdiagnose as "no market" or "Gateway login."

## What we changed

- Rewrote `scripts/Start-NovaDaily.ps1` ASCII-only with working recycle, health wait, STATUS line, browser-only-if-healthy
- `Start-NovaApi.ps1` default: hidden + file redirect (QuickEdit-safe); `-Interactive` for Tee
- `Stop-NovaPorts.ps1` surfaces taskkill exit codes
- `IBKR_COMPLETED_ORDERS_MIN_INTERVAL_SEC=300` cooldown; connect uses `force=True`
- `logging_setup.py` QueueHandler / QueueListener; shutdown from lifespan
- `backend/tests/test_scripts_ascii.py` + cooldown tests; `py-spy` in requirements-dev
- PROBLEM_LOG OPEN/DEFERRED for premarket-before-04:00

## How it works now

At 6 AM, NovaDailyStart parses cleanly under powershell 5.1. If :8000 listens but `/api/health` fails, Stop-NovaPorts kills the tree and a fresh API starts hidden. Closed Orders empty polls no longer each fire `reqCompletedOrdersAsync`. Hot-path log records enqueue to a listener thread so the asyncio loop stays free for health probes.

## Why this approach

- Fixed the recycle encoding root cause rather than adding another watchdog process -- the 6 AM task already existed; it just could not execute its recycle branch.
- Cooldown on completed-orders (not removing the warm-up) preserves Closed Orders correctness after connect while stopping the empty-poll flood.
- QueueListener keeps full log fidelity without sync I/O on the loop (rejected: deleting HOD TRADE logs -- needed for parity debug).
- Deferred overnight Gateway / pre-04:00 product work to a labeled OPEN issue so this session stayed focused on the wedge recurrence the user hits after login.

## Verification

- `pytest backend/tests/test_ibkr_account.py backend/tests/test_scripts_ascii.py backend/tests/test_closed_orders.py` -- 36 passed
- ASCII byte check on critical `.ps1` files
- PowerShell parser: `Start-NovaDaily.ps1` PARSE_OK

## Follow-ups

- OPEN: Premarket stack must be up before 04:00 ET (no manual morning start) -- PROBLEM_LOG
- Optional: restart the live API process so cooldown + QueueListener load without waiting for tomorrow's daily start
- py-spy dump on next zero-CPU stall if any remains

## Keywords

API_WEDGED, NovaDailyStart, completed-orders, QueueHandler, morning wedge, premarket deferred
