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
- [ ] Slippage budget documented in constants / risk notes

**Current:** Not certified. **NO-GO.**

### Restart reconciliation

- [ ] Kill API / process restart → mode resets to `signal`
- [ ] `nova_os.recovery.run_startup_recovery` reconstructs open paper positions or force_signal on ambiguity
- [ ] Drill logged in PROBLEM_LOG / journal with date

**Current:** P5 recovery implemented; keep drilling, but alone does not authorize live. Partial ✓ for paper only.

### Emergency drills

- [ ] Flatten with typed `FLATTEN` token practiced
- [ ] Kill / disarm drops to signal and cancels automation
- [ ] Operator can reach IB Gateway disconnect without UI

**Current:** Controls exist (P4/P5); live emergency on real capital not approved. **NO-GO for live.**

### Archive integrity

- [ ] Local cold days compact + `restore_day_to_temp` ok
- [ ] R2 configured (`R2_*` in `.env` only) and `GET /api/archive/health` → verified days present
- [ ] `ARCHIVE_REQUIRE_VERIFIED_BEFORE_TRIM` remains True until remote verify is routine
- [ ] At least one replay day reviewed via `tools/nova_os_replay.py`

**Current:** Code paths ready; operator must still add R2 keys. Integrity not yet production-proven. **NO-GO.**

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

## Next action

**Stop.** A separate, explicitly approved phase is required before any live-money automation work. Do not start “P11 live” from habit — wait for operator GO after checklist greens.
