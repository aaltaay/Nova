# 2026-07-28 -- Phase B waived; Phase K short entry E2E (K0-K4)

- **Status:** completed (code + docs; K3 human paper days still open)
- **Agents:** parent (in-session, zero-hop)
- **Domain:** roadmap / execution / IBKR / Stock View UI
- **Related:** `CHANGELOG.md` 2026-07-28 Phase B waived; Phase K E2E · ADR 009 · `Nova-Roadmap-Status.md` Phase K

## Task

User waived Phase B ("cancel or complete, I don't want it") and asked for a full end-to-end Phase K plan that implements every short-entry gap (testability, validity, safety, paper/live, UI next to L2).

## Goal

Phase B marked WAIVED (honest, not fake-complete). Phase K K0-K4 code/docs shipped: ADR + constitution, shortability truth, execution gates, flatten cover, Shortability chip + Long/Short ticket. K3 human evidence rows remain empty until real paper short days.

## Why it mattered

Without an explicit short gate, removing anti-short would break flatten/reconcile. Without UI shortability next to L2, operators cannot see borrow state at decision time. Without waiving B honestly, Phase K would stay falsely gated on paperwork the user declined.

## What we changed

- Waived Phase B in ledger + protocol stamps + adjacent status pointers
- ADR 009 + AGENTS invariant #7 + ADR 007 pointer
- `backend/ibkr/shortability.py` + listing payload enrich; `IBKR_SHORTABILITY_TTL_SEC`
- `IBKR_SHORT_ENABLED`, `ExecutionCommand.short_entry`, validate `SHORT_*` codes
- Short brackets entry side; `account.short_qty`; flatten market BUY cover
- Stock View Shortability chip + ManualOrder Long/Short direction
- Tests: shortability + validate matrix + Vitest chip

## How it works now

SELL without `short_entry` still refuses flat/oversell. Short opening needs env + opt-in + fresh `shortable_est`. Chip shows IBKR estimate beside L2; Short toggle disabled with mirrored reason when blocked. Live short still needs K3 sign-off + `IBKR_LIVE_TRADING_CONFIRMED`. `auto_live` NO-GO.

## Why this approach

- Waive not complete: inventing shadow days would rewrite history
- Explicit `short_entry` not inference: keeps anti-short refusals meaningful
- Third env key: matches existing two-key spend pattern
- Fail-closed thin/unknown/stale: prefer refuse over silent HTB fills
- K3 human days not invented: same honesty as waived B

## Verification

- `pytest tests/test_shortability.py tests/test_execution_validate.py tests/test_listing_compare.py` -- 19 passed
- Vitest `ShortabilityChip.test.tsx` -- 2 passed

## Follow-ups

- Run ≥3 paper short days; fill K3 Evidence; operator sign-off before live short
- Journal `side="short"` on automation short fills when short setups exist
- Scanner shortable filter (deferred)

## Keywords

phase k, short entry, shortability, IBKR_SHORT_ENABLED, tick 236, waive phase b, ADR 009, flatten cover, shortability chip
