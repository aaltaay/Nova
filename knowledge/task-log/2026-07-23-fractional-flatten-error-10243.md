# 2026-07-23 — Block fractional Flatten + hard-fail Error 10243 cancel

- **Status:** completed
- **Agents:** parent
- **Domain:** execution / IBKR trading
- **Related:** `CHANGELOG.md` § 2026-07-23 Block fractional Flatten · `PROBLEM_LOG.md` § 2026-07-23 Error 10243 · transcript 2026-07-21 live Flatten of 0.0642 IBKR

## Task

Implement (1) preflight block of fractional share Flatten/place and (2) hard-fail when IBKR cancels with Error 10243 / no fill; log the historical incident.

## Goal

Operators never get a silent “success” when IBKR refuses a fractional API order; they get a clear message to close leftovers in TWS/Gateway desktop.

## Why it mattered

Live Flatten of `0.0642` IBKR was submitted, then cancelled by IBKR with Error 10243. The leftover stayed open and the UI could treat `broker_status: Cancelled` as success.

## What we changed

- `constants_ibkr.py`: `IBKR_ERROR_FRACTIONAL_API=10243`, `IBKR_FRACTIONAL_ORDER_API_MSG`
- `execution.validate`: reject non-whole place qty (`QTY_FRACTIONAL_API`)
- `execution.telemetry`: record `errorEvent` on order watches; `TERMINAL_REJECT_STATUSES`
- `execution.broker_send.finish_place`: `ok=false` on Cancelled/ApiCancelled/Inactive with no fill
- FE `exitPosition.buildExitFullPosition`: same preflight before place
- Tests + PROBLEM_LOG / CHANGELOG

## How it works now

Whole-share lots go through the existing ADR 007 path. Fractional qty never leaves validation (backend) or exit builder (FE). If a cancel-without-fill still arrives (race / older client), the receipt is a hard failure with the 10243 desktop message when the error code is present.

## Why this approach

- **Preflight + post-ack fail:** IBKR cannot be overridden; preflight stops the round-trip, post-ack covers anything that still lands as Cancelled.
- **Rejected** auto-rounding fractional leftovers to 0 or 1 — rounding to 0 does nothing; rounding up would invent a short; rounding down leaves a stub. Desktop close is the only correct close for true fractionals.
- **Rejected** treating every Cancelled as success forever — that was the UX lie on 2026-07-21.

## Verification

- `py -3 -m pytest tests/test_execution_validate.py tests/test_execution_finish_place_reject.py -q` — 13 passed
- `npx vitest run src/ibkr/exitPosition.test.ts src/ibkr/closeFullPosition.test.ts` — 10 passed

## Follow-ups

Close any remaining fractional leftover in TWS/Gateway desktop (API cannot do it). Optional: surface `reason_code` in Flatten toast copy (error string already sufficient).

## Keywords

Error 10243, fractional shares, Flatten, QTY_FRACTIONAL_API, finish_place, Cancelled, IBKR leftover
