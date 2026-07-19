# Nova OS Live-Readiness Review (P10)

> **Date:** 2026-07-15  
> **Scope:** Docs-only GO/NO-GO for `auto_live`. Does not unlock live money.  
> **Canonical status:** [[Nova-OS-Status]]

## Verdict

### **NO-GO for `auto_live`**

Nova OS must **not** enable automatic live order placement.

| Fact | Evidence |
|------|----------|
| `auto_live` is rejected in code | `nova_os.control_mode.set_mode("auto_live")` raises `ValueError` — live money stays blocked |
| Paper sample insufficient | Journal go/no-go and paper auto path exist (P5), but there is no approved multi-week expectancy / adherence dataset that clears live criteria |
| Archive learning loop just landed | P6–P9 (capture → cold → R2 stubs → replay) are code-complete; remote durability still needs operator R2 keys; replay findings are heuristic only |
| Explicit product rule | Live requires separate approved phase + `IBKR_LIVE_TRADING_CONFIRMED` — P10 is review only |

**Recommendation:** Remain on `signal` / `confirm` / `auto_paper` (paper Gateway). Treat any future live unlock as a **new approved phase**, not a silent follow-on to P10.

---

## Checklist (must all be green before any future GO)

### Paper sample size

- [ ] Minimum closed paper trades logged (non-mock) — target: **≥ 50** closed brackets under Nova OS decide → executor path
- [ ] Sample spans **≥ 15** distinct RTH sessions
- [ ] Mix of setups (Gap-and-Go / Bull Flag / ABCD) represented — not one lucky pattern

**Current:** Insufficient / not proven in-repo as a durable metrics ledger for live. **NO-GO.**

### Expectancy

- [ ] Net expectancy after costs/slippage estimate is positive over the paper sample
- [ ] Breakdown by setup + session window reviewed
- [ ] Evening-review heuristic (`archive.evening_review`) is **not** treated as expectancy proof

**Current:** No certified expectancy report tied to policy version. **NO-GO.**

### Adherence

- [ ] ≥ 90% of paper entries match staged/approved ticket (entry/stop/target) without discretionary override
- [ ] Loss-policy downgrades (1st loss → confirm, 3rd → halt) observed and journaled correctly

**Current:** Loss policy + confirm/auto_paper paths exist; adherence not formally scored for live. **NO-GO.**

### Slippage

- [ ] Measured fill vs ticket entry on paper (and any limited live probes under manual confirm)
- [x] Slippage budget documented in constants / risk notes — `SLIPPAGE_MAX_ADVERSE_BPS = 50` (measure in paper before GO)

**Current:** Budget constant only; measurement not certified. **NO-GO.**

### Restart reconciliation

- [x] Kill API / process restart → mode resets to `signal` — kill-switch drill 2026-07-17; mode remains `signal` (never persisted)
- [x] `nova_os.recovery.run_startup_recovery` reconstructs open paper positions or force_signal on ambiguity — covered by unit tests + lifespan wire
- [x] Drill logged — PROBLEM_LOG / CHANGELOG 2026-07-17 (kill + flatten-preview; no open positions to reconstruct)

**Current:** Code + API drills green. Keep re-drilling after first real paper open position.

### Emergency drills

- [x] Flatten with typed `FLATTEN` token practiced — `GET /api/strategy/executor/flatten-preview` 2026-07-17 (empty tracked positions; token `FLATTEN`)
- [x] Kill / disarm drops to signal and cancels automation — kill-switch + reset-kill-switch API drill 2026-07-17
- [ ] Operator can reach IB Gateway disconnect without UI

**Current:** API drills done on locked live Gateway (no spends). Operator still owes Gateway disconnect drill. **Partial.**

### Archive integrity

- [x] Local cold days compact + bars present — 2026-07-15/16 re-compacted after tape→1m backfill (59 + 272 `bars_1m` rows) 2026-07-17
- [x] R2 configured and `GET /api/archive/health` → verified days present
- [x] `ARCHIVE_REQUIRE_VERIFIED_BEFORE_TRIM` remains True
- [x] `walk_day('2026-07-16')` ran successfully (5 steps, symbols incl. AAPL) 2026-07-17 — operator still should review `tools/nova_os_replay.py` output in an evening session

**Current:** Bars feeder + R2 + walk_day smoke pass. Not a live unlock.

### PDT / account gates

- [ ] Account mode confirmed (`paper` vs `live`) before any mode raise
- [ ] Pattern-day-trader / buying-power constraints understood for the live account
- [ ] `IBKR_LIVE_TRADING_CONFIRMED=true` only after this review flips to GO **and** a separate unlock phase

**Current:** `auto_live` unavailable in `control_mode`. **NO-GO.**

---

## Control-mode confirmation

As of P10 close:

| Mode | Status |
|------|--------|
| `signal` | Available (default on restart) |
| `confirm` | Available |
| `auto_paper` | Available when paper Gateway + spend + risk + not holiday |
| `auto_live` | **Unavailable** — rejected in `set_mode` |

---

## Phase I — Evidence framework (2026-07-15)

Phase I does **not** unlock live. It freezes the GO thresholds operators must meet using Phase B (+ E/F) data.

| Metric | GO threshold | Source |
|--------|--------------|--------|
| Closed paper brackets (non-mock) | ≥ **50** | `GET /api/journal/metrics` |
| Distinct RTH sessions | ≥ **15** | Journal `closed_ts` days + shadow-day log |
| Setup mix | Gap-and-Go / Bull Flag / ABCD each represented | Journal `setup` + Reports tags |
| Net expectancy after costs/slippage estimate | **Positive** | Journal R-multiples + operator slippage notes |
| Ticket adherence | ≥ **90%** adherent entries | `adherence_pct` / Live-Readiness checklist |
| Loss policy observed | 1st loss → confirm, 3rd → halt | Executor + Nova OS receipts |
| Archive integrity | ≥1 real cold day compact + restore + `walk_day` | Phase C remainder |
| Backtest honesty | Archive backtests labeled no-hindsight / no spread | Phase E `/api/backtest/run` |

**Current Phase I state:** evidence **framework ready**; measured verdict still **NO-GO** until Phase B metrics exist (≥5 shadow days + sample size above).

**`auto_live`:** remains **rejected** in `backend/nova_os/control_mode.py`. No code change in Phase I.

### Execution path proof (2026-07-17, not a live unlock)

ADR 007 centralized every broker mutation behind `execution.service.execute` with idempotency + stage timings. Synthetic receive→ack p95 passed (≤250 ms). Verdict in `docs/trading-execution-validation.md`: **Continue** (architecturally ready for a *separately approved* one-share live probe). This does **not** flip Phase I to GO and does **not** authorize `auto_live`.

---

## Next action

**Stop.** A separate, explicitly approved phase is required before any live-money automation work. Do not start “P11 live” from habit — wait for operator GO after checklist greens.
