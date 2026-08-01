# 2026-07-31 — Sentry usefulness hardening (quiet inbox + ops-once)

- **Status:** completed
- **Agents:** parent (Grok audit subagents + implement)
- **Domain:** observability / IBKR
- **Related:** `CHANGELOG.md` §2026-07-31 Sentry usefulness · `PROBLEM_LOG.md` §2026-07-31 Sentry ERROR-log flood

## Task

Make Sentry useful after a full audit: stop ~55k/week IBKR reconnect/scanner ERROR noise, keep real product signal, one ops-once session health event.

## Goal

Quiet inbox + `environment=local` + ops-once `ibkr.session.unusable` / max-tickers fingerprints; historical noise ignored; already-fixed `startReq` resolved.

## Why it mattered

Default `LoggingIntegration(event_level=ERROR)` + double bridge/runner ERROR logs + mislabeled `environment=production` made the high-priority email alert a reconnect pager. Real bugs were invisible.

## What we changed

- `observability.py`: explicit LoggingIntegration, `environment`/`release`, `before_send`, ops-once capture helpers
- `observability_filters.py`: denylist for bridge/keep-cache, yfinance, WS close, provider shell, etc.
- Expanded `IBKR_BENIGN_*` (200/202/322/326/366/504/1100–1102/10349, unknown reqid)
- Bridge + scanner runners: ERROR → WARNING for keep-cache
- `session_errors`: 1100/101 WARNING + fingerprinted captures on first stamp / max tickers
- Client intake: stack extra, fingerprint, provider-shell ignore; FE dispose/provider filter
- WS send-after-close treated as disconnect
- Sentry: bulk ignore noise; resolve startReq + stale ImportError
- `.env` / `.env.example`: `SENTRY_ENVIRONMENT=local`

## How it works now

ERROR logs still can create Issues, but expected IBKR churn is WARNING or denylisted. Gateway down → at most one fingerprinted `ibkr.session.unusable` per cooldown. Local `blast.log` stays loud. Client stacks reach Sentry for real UI bugs.

## Why this approach

Source-level downgrade + `before_send` safety net (Sentry docs). Rejected `event_level=None` (blinds real `logger.exception`). Rejected frontend SDK until backend inbox is clean. `startReq` was already fixed in `7d64e27` -- resolve not re-implement.

## Verification

- `pytest` observability / log_filters / client_errors / ws_close / session_errors -- 42+ passed
- Vitest `reportClientError.test.ts` -- 5 passed
- Sentry unresolved inbox reduced to product/client ReferenceErrors + PermissionError + recovery ambiguous + account-summary 322

## Follow-ups

- **Manual:** disable Sentry alert 3710085 (high-priority email, freq 0) in UI -- no API token in env for rule updates
- Optional: replace with first-seen real-exception alert after overnight quiet
- Restart API so new filters load
- Triage remaining client `is not defined` / `toLowerCase` issues as product or Vite HMR

## Keywords

Sentry, before_send, LoggingIntegration, BenignIbkr, bridge keep-cache, session_unusable, environment=local
