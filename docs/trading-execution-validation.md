# Trading execution validation (ADR 007)

> **Date:** 2026-07-17  
> **Scope:** Centralize every broker mutation behind one measured path; prove safety and paper/synthetic latency. **No live orders.**  
> **ADR:** `architecture/decisions/007-centralized-trading-execution.md`  
> **Canvas:** `agent-execution.canvas.tsx`

## Verdict: **Continue** (architecturally ready for a separately approved one-share live probe)

| Criterion | Result |
|-----------|--------|
| Single entry path (`execution.service.execute`) | Pass |
| Duplicate / concurrent idempotency | Pass (unit) |
| Account / risk / live-unconfirmed gates | Pass (unit) |
| Persist-before-send | Pass (unit) |
| Callback ack ≠ `PendingSubmit`; fill correlation | Pass (unit) |
| Paper/live same code path; only gates/credentials differ | Pass (unit) |
| AST: no production `placeOrder`/`cancelOrder` outside adapter | Pass |
| Synthetic p95 receive→ack ≤ 250 ms | **Pass** (~53 ms @ 50 place+cancel samples) |
| Paper Gateway p95 | Not run this session (needs logged-in paper Gateway + `--confirm-paper-orders`) |
| Live fill / slippage parity | **Not claimed** — IBKR paper fills are simulator-based |

**Still NO-GO for `auto_live`.** This proof does not unlock live money.

## Before / after path map

| Caller | Before | After |
|--------|--------|-------|
| Manual UI `POST /api/ibkr/order` | `ibkr.orders.place_order` (bypassed risk) | `execute(place, source=manual, skip_risk)` |
| Manual cancel | `orders.cancel_order` | `execute(cancel)` |
| Price replace | Missing | `PATCH /api/ibkr/order/{id}` → `execute(replace)` |
| Staged approve / auto_paper | `place_bracket_order` via executor | `execute(bracket)` + idempotency key |
| Kill / cancel-working / flatten | Direct cancel/place | `execute` with `source=kill\|flatten` |

## Stage latency (synthetic, 2026-07-17)

Command: `py -3 tools/execution_latency_probe.py --confirm-paper-orders --synthetic --samples 50`

| Stage | p50 (ms) | p95 (ms) | max (ms) |
|-------|----------|----------|----------|
| Validation | ~30 | ~32 | ~34 |
| Broker sent | ~40 | ~46 | — |
| Broker ack | ~49 | **~53** | ~54 |

SLA target: p95 ack ≤ 250 ms (excludes fill).

## How to re-run paper Gateway probe

1. Log into IB Gateway **paper**, `spend_status=paper_armed`, `IBKR_LIVE_TRADING_CONFIRMED` unset.
2. `py -3 tools/execution_latency_probe.py --confirm-paper-orders --samples 50`
3. Probe cancels non-marketable 1-share limits; aborts if live confirmed.

## Limits

- Paper acknowledgment latency ≠ live exchange ack or fill quality.
- Manual place still skips Nova OS risk/concurrency (IBKR safety + account gates only) — intentional for the ticket UI.
- Fill poll (10s) remains a reconciliation backstop; primary fill mark is `execDetails` / `Filled` → ledger.
