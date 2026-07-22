# 2026-07-22 — Quiet Sentry IBKR/chart dispose noise

- **Status:** completed
- **Agents:** parent
- **Domain:** observability / IBKR
- **Related:** `CHANGELOG.md` §2026-07-22 Quiet Sentry · `PROBLEM_LOG.md` §2026-07-22 Sentry flooded

## Task

User reported Sentry was yelling; triage `altay-studio` / `python-fastapi` and stop expected Gateway/reconnect/chart noise from opening ERROR issues.

## Goal

Downgrade known-benign IBKR log ERROR spam before Sentry LoggingIntegration, ignore TradingView dispose races at client intake, leave real capacity signals (Error 101) as ERROR, and clean matching unresolved issues in Sentry.

## Why it mattered

Tens of thousands of expected events (late cancel EId 300, mdata subscription 10089, Gateway port refuse, chart dispose) drowned actionable issues like max-tickers oversubscription and real AttributeErrors.

## What we changed

- Expanded `IBKR_BENIGN_LOG_ERROR_CODES` to 162, 365, 300, 354, 10089, 10189
- Added message needles for open/completed-orders timeouts, Gateway API-port hint, ConnectionRefused, peer closed
- Client intake: ignore `Object is disposed`
- Tests for new needles + keep Error 101 non-benign
- Sentry: resolve/ignore issues that match the new filters

## How it works now

`BenignIbkrErrorFilter` still attaches to noisy `ib_async.*` loggers and downgrades matching ERROR → WARNING (local logs keep the text; Sentry event_level no longer fires). `/api/client-errors` drops dispose races like Vite HMR noise. Error 101 max-tickers remains an ERROR for product budgeting work. Restart API to load constants.

## Why this approach

Filter at the log/client boundary (same pattern as 162/365) rather than silencing whole loggers or dropping ERROR globally — preserves local diagnostics and leaves capacity/product bugs visible. Rejected treating Error 101 as benign (real oversubscription). Rejected ignoring all Error 322 (scanner-quota vs account-summary are different product signals).

## Verification

- `py -3 -m pytest tests/test_ibkr_log_filters.py tests/test_client_errors.py -q` → 19 passed
- Sentry search unresolved last 24h (freq) for triage

## Follow-ups

- Error 101 / Error 322 scanner-quota: HOD/scanner subscription budgeting (product)
- AttributeError `includeExpired` (PYTHON-FASTAPI-11Z): real bug
- Yahoo 404 spam for odd symbols: separate noise pass
- Restart uvicorn so new filters load; then historical noise issues stay ignored/resolved

## Keywords

Sentry, IBKR_BENIGN_LOG_ERROR_CODES, Error 300, Error 10089, Object is disposed, client_errors, PYTHON-FASTAPI
