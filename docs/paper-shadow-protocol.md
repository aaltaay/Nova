# Phase B — Paper shadow protocol

Ops-only window. **No product features. No `auto_live`. No live money.**

Canonical status: `knowledge/obsidian/03-Nova-Decisions/Nova-Roadmap-Status.md`  
Plan: `nova_master_roadmap_a_z.plan.md`  
Day log template: `docs/shadow-day-log-template.md`  
UI: Executor control ladder in `frontend/src/strategy/ExecutorPanel.tsx`  
Mode gate: `backend/nova_os/control_mode.py`

---

## Goal

Prove Nova OS paper behavior across real market sessions:

1. Run the control ladder `signal` → `confirm` → `auto_paper`
2. Review each completed day
3. Log findings and self-anneal bugs
4. Accumulate **≥ 5** shadow days with review artifacts before Phase B exit

---

## Hard bans

| Ban | Why |
|-----|-----|
| **`auto_live`** | Rejected in `control_mode.set_mode` — live money stays blocked |
| **Live Gateway orders / live unlock flags** | Phase B is paper only (`IBKR` paper account) |
| **Arming for live or “just testing” live** | Separate approved phase required after evidence |
| **Skipping evening reviews** | Days without review artifacts do not count toward the ≥5 exit |
| **Silent feed fallbacks** | Discovery=`ibkr` stays IBKR-only (see `.cursor/rules/single-market-data-feed.mdc`) |

If empty scanners look like “no gaps,” check IBKR first — see **IB Gateway login** below.

---

## Prerequisites

1. App running (`Run Nova.bat` or uvicorn + Vite) — UI `http://localhost:5173`, API `http://127.0.0.1:8000`
2. **IB Gateway logged in** on the **paper** port when discovery is `ibkr` (usual paper API port `4002`)
3. `IBKR_ENABLED` / order flags appropriate for **paper** only — never set live-confirm flags for this protocol
4. Archive maintenance on if you want cold days for review: `ARCHIVE_MAINTENANCE_ENABLED=true` (local `.env`)

### ACTION REQUIRED — IB Gateway login

If `GET /api/ibkr/status` shows `"connected": false` while discovery is `ibkr`, gappers/movers will look empty. That is a **login blocker**, not a quiet market.

- Complete Gateway username/password and IBKR Mobile 2FA if prompted
- See `.cursor/rules/ibkr-gateway-login-warning.mdc` and Trading tab onboarding copy
- Agents must warn loudly — do not “debug the scanner” in silence

---

## Control modes (what each means)

| Mode | Behavior | When to use in Phase B |
|------|----------|------------------------|
| `signal` | Decide + journal; **no** order placement | Start of day / default after restart |
| `confirm` | Stages tickets; **you** approve/reject | Mid ladder — practice human gate |
| `auto_paper` | Auto-places on **paper** Gateway when gates pass | Only after signal/confirm comfort that session |
| `auto_live` | **Blocked** — `POST` mode returns 409 | Never in Phase B |

API:

```http
GET  /api/strategy/executor/status
POST /api/strategy/executor/mode
Content-Type: application/json

{"mode": "signal"}
```

Same ladder is available in the Executor / Automate UI (`setMode`).

`auto_paper` requires paper Gateway + spend/risk gates (`auto_paper_gate_status` in `control_mode.py`). If set_mode fails, fix the gate reason — do not switch to live.

---

## Suggested day script

### Morning / open

1. Confirm IBKR connected: `GET /api/ibkr/status` → `"connected": true`, paper account
2. Confirm executor: `GET /api/strategy/executor/status` — note `effective_mode` (restarts → `signal`)
3. Start in **`signal`** — watch decisions / attention strip; no orders
4. After you trust the session tape: move to **`confirm`** — approve/reject staged tickets deliberately
5. Only if paper gates are green and you intend auto placement: **`auto_paper`**
6. Kill-switch / typed `FLATTEN` remain available — use them if anything looks wrong

### During the session — record

For each notable decision or trade, jot:

- Symbol, time (ET), setup if known
- Mode at the time (`signal` / `confirm` / `auto_paper`)
- What Nova decided (`BUY` / `WAIT` / `NO_BUY`) vs what you would have done
- Fill / reject / cancel outcome (paper)
- Any UI/API bug (file in `PROBLEM_LOG.md` after fix, or a stub note until fixed)

Keep notes in the shadow-day log section of `Nova-Roadmap-Status.md` History (or a dated row under Phase B Evidence).

### Evening review (after the session)

When a cold/compacted day exists for `YYYY-MM-DD`:

```http
GET /api/archive/health
GET /api/archive/days
GET /api/archive/review/{YYYY-MM-DD}?limit=10
GET /api/archive/walk/{YYYY-MM-DD}?limit=5&step_min=5
GET /api/archive/ask?session_date=YYYY-MM-DD
```

Python (from `backend/`):

```python
from archive.evening_review import evening_review
from archive.replay import walk_day

evening_review("YYYY-MM-DD")
walk_day("YYYY-MM-DD", max_symbols=5, step_min=5)
```

Review is **heuristic** — not expectancy proof for live. Use it to catch decision/process bugs and journal gaps.

If no compacted day yet: still log the shadow day (modes used, paper outcomes, bugs). Phase C remainder covers first real `walk_day` on a production cold day.

---

## Where to log findings

| Finding type | Where |
|--------------|--------|
| Day completed + modes + review links | `Nova-Roadmap-Status.md` → Phase B evidence + History append |
| Bug / incorrect behavior | Fix → `PROBLEM_LOG.md` + `CHANGELOG.md` (self-anneal) |
| Live-readiness metrics over time | Feed Phase I later; do **not** unlock `auto_live` here |
| Archive upload / restore issues | Phase C remainder + `docs/r2-archive-setup.md` |

---

## Exit criteria (Phase B)

- [ ] ≥ **5** market days with recorded shadow notes
- [ ] Ladder exercised across days (`signal` → `confirm` → `auto_paper` as appropriate)
- [ ] Evening review attempted when archive days exist
- [ ] Bugs annealed or tracked; `auto_live` still NO-GO
- [ ] Status note + CHANGELOG updated; commit + push per continuity rule

Then stop. Next phase is **not** live — typically Phase C remainder and/or Phase A skills per the Master Roadmap.

---

## Related

- `.cursor/rules/nova-roadmap-continuity.mdc`
- `.cursor/rules/nova-os-continuity.mdc`
- `.cursor/rules/ibkr-gateway-login-warning.mdc`
- `knowledge/obsidian/03-Nova-Decisions/Nova-OS-Live-Readiness-Review.md` (still NO-GO)
- `knowledge/obsidian/03-Nova-Decisions/Nova-OS-Archive-Restore-Runbook.md`
