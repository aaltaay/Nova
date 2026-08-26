# 2026-08-26 -- Buying-power reject pop-up + dead API lock

- **Status:** completed
- **Agents:** parent
- **Domain:** execution | ibkr-ops
- **Related:** `CHANGELOG.md` 2026-08-26 -- Buying-power rejects pop up · `PROBLEM_LOG.md` 2026-08-26 -- Buying-power reject had no pop-up · 2026-08-26 -- Instance lock false-alive PID

## Task

Check the audit trail for a just-placed order that showed `estimated notional 596.54 exceeds BuyingPower 552.79`, and make that class of notice a pop-up.

## Goal

Tell the operator what happened to the order, then make the next reject impossible to miss.

## Why it mattered

A live BUY can fail before IB ever sees it. If the only UI is a tiny footer span, it looks like the click did nothing.

## What we changed

- Read live Activity: execution `d29f349d-8b48-404f-b146-2e77cd261c91` META BUY 1 LMT @ 596.54, `status=rejected`, `reason_code=BUYING_POWER`, never sent.
- Added `notifyOrderRejected` (`alertApp`) on ticket, flatten, and Nova Action fails.
- Added `reason_code` to `legacy_place_dict` / `PlaceOrderResult`.
- Fixed `_pid_alive` so a killed API PID does not block restart (`GetExitCodeProcess`).
- Restarted the wedged sidecar (HTTP refused, IB still attached).

## How it works now

Nova still refuses a priced BUY when estimated notional > cached BuyingPower. That row stays on the Activity trail. The desk now also gets a blocking pop-up with a plain title. Confirm-dialog cancel does not pop. One API on :8000.

## Why this approach

Reused `alertApp` (already used for cancel/flatten/fill-now) instead of a second toast system. Inline footer stays as a breadcrumb. Did not loosen the BP gate. Infer BUYING_POWER from the error string so hotkeys pop even before every caller threads `reason_code`.

Rejected: Nova OS attention strip (easy to miss, wrong domain). `window.alert` (unstyled). Client-only BP check (backend is the spend gate).

## Verification

- Live GET `/api/ibkr/execution/d29f349d-...` rejected BUYING_POWER; account BP 552.79 / NL 559.
- Vitest `notifyOrderRejected` + host (11 passed); neighbors 30 passed.
- pytest `TestAccountAndRiskGates` 7 passed; `test_api_instance_lock` 5 passed.
- `npm run build` exit 0.
- After restart: IBKR `connected=true` `session_state=ready` live; movers 50 gainers live; gappers 20 live.

## Follow-ups

Do not treat this as a sizing bug -- 1 META share at $596 is more cash than the account has. Deposit or pick a cheaper name. Electron may need a refresh if it is not on Vite HMR.

## Keywords

BUYING_POWER, META, Activity, alertApp, notifyOrderRejected, api-instance.lock, GetExitCodeProcess
