# 2026-09-10 -- IBKR verification-required flow

- **Status:** completed
- **Agents:** parent
- **Domain:** execution
- **Related:** `CHANGELOG.md` 2026-09-10 IBKR verification-required flow; `PROBLEM_LOG.md` 2026-09-10 IBKR verification reject; GitHub D-013 and D-005

## Task

Implement an actionable response to IBKR Error 201 Client Portal token verification, with tests and no loss of exit capability.

## Goal

Turn the raw broker rejection into a typed operator workflow, prevent repeated entry sends while verification is unresolved, and keep cancel, replace, long exits, short covers, and flatten available.

## Why it mattered

A live AAPL order reached IBKR and was rejected for identity verification. Nova displayed the broker's raw uppercase message only after the attempt, which made a functioning order path look broken and gave the operator no safe recovery controls.

## What we changed

- Added a session-owned, per-symbol execution latch for the exact Error 201 token-verification message.
- Added a typed `IBKR_VERIFICATION_REQUIRED` receipt and a thin acknowledgment endpoint.
- Added an actionable dialog with order context, an official Client Portal button, explicit verification acknowledgment, and no automatic retry.
- Added an allowlisted Electron external-browser bridge so the portal button works in Desktop.
- Preserved rejection reason and order context through manual tickets, flatten feedback, and Nova Actions.
- Extracted manual submission into `useManualOrderSubmission.ts`, bringing `ManualOrderTicket.tsx` from 378 to 246 lines instead of growing an existing file-size violation.
- Added backend service, route, exit-safety, dialog, portal, acknowledgment, and hotkey tests.

## How it works now

IBKR must reveal this restriction through an order error; a healthy Gateway status cannot predict it. When the exact Error 201 arrives, Nova records a failed receipt and latches that symbol. Later risk-increasing entries stop before broker send and receive the same typed reason. The operator opens the official portal, verifies, and clicks "I've completed verification"; only that acknowledgment clears the latch. Exits and order management never consult the entry block.

## Why this approach

The latch lives behind the centralized ADR 007 execution service, so UI, hotkeys, and automation cannot bypass it. It is per-symbol because IBKR said "this security," and it is session-scoped because IBKR exposes no reliable API state proving that identity verification is complete. A What-If order was rejected as a hard dependency because IBKR only documents it for margin and commission, not identity restrictions, and it would add latency to every trade. Automatic retry was rejected because it could place a live order after the operator's intended moment.

## Verification

- Red phase: focused pytest failed because `execution.verification_gate` did not exist; focused Vitest failed on the missing verification title/actions.
- `py -3 -m pytest backend/tests/test_execution_verification_gate.py backend/tests/test_execution_verification_service.py backend/tests/test_routes_trading_verification.py backend/tests/test_execution_finish_place_reject.py -q`
- `npm test -- --run src/ibkr/notifyOrderRejected.test.ts src/ibkr/notifyOrderRejected.host.test.tsx src/ibkr/openIbkrClientPortal.test.ts src/ibkr/acknowledgeVerification.test.ts src/hotkeys/runNovaAction.test.ts`
- Full backend: 1,493 passed.
- Full frontend: 878 passed across 180 files.
- `npm run build` passed.
- `py -3 tools/doc_invariants.py` and `py -3 tools/maintainer_checks.py --fail-on-kind ib_loop_sync_io` passed.
- Browser: loaded the local Vite app and invoked the dialog module directly, without sending an order; title, LIVE BUY 1 AAPL context, portal/close/acknowledgment controls, and dismissal rendered correctly.
- `npm run lint` remains red only on the pre-existing D-029 baseline (four errors in untouched `barsStore.ts`, `chartDrawingsStore.ts`, and `effectiveBindings.ts`).

## Follow-ups

D-013 remains open for its separate spend-lock, FastAPI `detail`, and unknown-status-tone items. App verification reproduced existing D-005 three times: the API PID retained established sockets and the instance lock after its 8000 listener vanished. Each confirmed stale PID was stopped; the final restart is performed only after tests and git work finish. No new work was parked.

## Keywords

IBKR, Error 201, Client Portal, verification token, broker reject, entry latch, exits, Electron openExternal
