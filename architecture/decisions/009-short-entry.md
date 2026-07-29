# ADR 009 — Short entry (IBKR short selling)

**Status:** Accepted · **Date:** 2026-07-28  
**Roadmap:** Phase K (`Nova-Roadmap-Status.md`) · builds on [[007-centralized-trading-execution]]

## Context

IBKR can short stocks; Nova deliberately cannot. `execution/validate.py` treats every non-flatten `SELL` as position-reducing against `account.long_qty()` (`NO_POSITION` / `OVERSELL`). Bracket automation hardcodes `EXECUTOR_ENTRY_SIDE_IBKR = "BUY"`. Listing flags already surface IBKR tick 236 (`shortableShares`) for display only.

The operator wants short entry with: shortable / HTB visibility next to Level 2, safe paper-first then live, and a single SSOT for gates. Opening shorts by "removing the anti-short check" would break flatten/reconcile, which assume SELL is risk-reducing.

## Decision

1. **Same execution path.** All short spends enter `execution.service.execute` (ADR 007). No second broker path.
2. **Explicit per-order opt-in.** `ExecutionCommand.short_entry: bool = False`. Never infer short intent from `side == SELL` + flat position.
3. **Env gate.** `IBKR_SHORT_ENABLED` (default `false`) via `ibkr.safety.short_enabled()`. Paper and live both require it. Live additionally requires `IBKR_LIVE_TRADING_CONFIRMED` (existing).
4. **Default anti-short unchanged.** No `short_entry` → existing `NO_POSITION` / `OVERSELL` / `POSITION_UNAVAILABLE`. `source=flatten` semantics for long exits unchanged.
5. **Shortability truth module.** IBKR tick 236 only. States: `shortable_est` (≥10k shares), `thin` (0–10k), `htb_likely` (≤0), `unknown` (no tick/error/disconnected). Freshness TTL; fail closed on `unknown` / stale / `thin` / `htb_likely`. Alpaca `shortable` / `easy_to_borrow` is never an IBKR locate.
6. **Reason codes.** Short-opening refusals use `SHORT_DISABLED`, `SHORT_NOT_SHORTABLE`, `SHORT_STALE_BORROW` (plus existing codes). Every refusal leaves a receipt.
7. **Short brackets.** When `short_entry`, entry side is `SELL`; protective legs invert; journal `side="short"`; PnL/R math side-aware.
8. **Buy-to-cover / flatten-from-short.** BUY that reduces a short is allowed up to short qty. Flatten covers shorts with market BUY (`source=flatten`).
9. **UI.** Shortability chip beside Level 2 (estimate + staleness + TWS confirm tooltip). Order ticket Long/Short; Short sends `short_entry=true` and disables with mirrored reason codes when blocked.
10. **Paper before live short.** K3: ≥3 paper short days + kill/flatten/reconnect drills + operator sign-off before live short. `auto_live` remains rejected.

## Consequences

- `validate.check_account_and_position` gains a short branch gated by `short_entry` + env + fresh `shortable_est`.
- `ibkr/account.py` exposes short qty (signed or dedicated helper) for cover/flatten; long SSOT for anti-short stays `long_qty()`.
- `status_snapshot()` exposes `short_enabled` for UI.
- Listing/ticker payload carries shortability `state`, `fetched_at`, `stale`.
- Scanner-level shortable filter is out of scope (Phase K deferred).

## Rejected alternatives

- Infer short from SELL-with-no-position (makes every oversell look intentional)
- Reuse only `IBKR_ORDERS_ENABLED` without a short-specific env (one flip opens shorts with all other spends)
- Treat Alpaca ETB as IBKR locate
- Allow `thin` / `unknown` with a warning (fail-open)
- Separate paper vs live short code paths
- Fake-complete Phase B to unlock K (B waived honestly instead)

## Related

- `backend/execution/validate.py`, `backend/ibkr/shortability.py`, `backend/ibkr/safety.py`
- `frontend/src/stock_view/StockViewDepthTape.tsx`, `frontend/src/ibkr/ManualOrderTicket.tsx`
- Phase K ledger in `knowledge/obsidian/03-Nova-Decisions/Nova-Roadmap-Status.md`
