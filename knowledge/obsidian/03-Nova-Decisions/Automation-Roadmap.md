# Automation Roadmap

> **Canonical Nova OS progress:** see [[Nova-OS-Status]] and the project homepage canvas (`nova-home.canvas.tsx`). This note is the historical A–F backbone; Nova OS phases P0–P10 extend it.

## Phase 0 — Memory (done)



## Phase A–F — Strategy backbone (done)

See [[Automation-Strategy-Backbone]] for detail.

- [x] **A** — Watchlist dashboard (`backend/strategy/watchlist.py`)
- [x] **B** — Setup trigger engine (Gap-and-Go, Bull Flag, ABCD)
- [x] **C** — Risk / discipline engine (`backend/strategy/risk.py`)
- [x] **D** — Paper execution via IBKR (`backend/strategy/executor.py`, binary arm)
- [x] **E** — Journal + go/no-go bar (`backend/journal/`)
- [x] **F** — Level 2 learning (record only; `backend/l2/`)

## Nova OS — phased plan (P0–P10)

| Phase | Focus | Status |
|-------|--------|--------|
| P0 | Baseline, status note, continuity rule, mission canvas, doc reconcile | **verified** |
| P1 | Event log, reason codes, loss-policy constants | **verified** |
| P2 | `decide()` brain, API, stream wiring (signal only) | **verified** |
| P3 | DecisionPanel, CLI, notifications framework | **verified** |
| P4 | Confirm mode + emergency controls | **verified** |
| P5 | Auto paper + restart recovery | **verified** |
| P6 | Loss-aware local capture (`backend/archive/`) | **verified** |
| P7 | Local cold archive (JSONL + manifests) | **verified** |
| P8 | Cloud durability (R2 code + docs; keys optional) | **verified** |
| P9 | Replay, rewind, ask, evening review | **verified** |
| P10 | Live-readiness review (GO/NO-GO only) | **verified — NO-GO for auto_live** |

Full map: Nova OS plan in `.cursor/plans/` and [[Nova-OS-Decision-Brain]]. Live unlock requires a **separate approved phase** after [[Nova-OS-Live-Readiness-Review]].

## Legacy phase labels (superseded by Nova OS map)

The rows below were the original roadmap before backbone A–F shipped. They are kept for context only.

### Phase 1 — Signal only (superseded by A–B + future P2)

- [x] Encode strategy filters on scanner / watchlist
- [x] Alert / UI when setup valid
- [x] Log signals to journal

### Phase 2 — Paper execution (superseded by D + future P4–P5)

- [x] Map signal → bracket ticket (executor)
- [x] Hard risk caps + IBKR safety gates
- [x] Journal results (trades table + metrics)

### Phase 3 — Tighten (Nova OS P2–P10)

- [x] Graduated control modes (`signal` / `confirm` / `auto_paper`; `auto_live` blocked)
- [x] Nova OS decide() with full gate audit
- [x] Permanent archive + replay (local + R2 stubs)
- [ ] Live only after explicit GO + separate unlock phase (requires `IBKR_LIVE_TRADING_CONFIRMED`) — **NO-GO as of P10**

<!-- AGENT_DREAM_FOOTER_START -->
**Last agent dream pass:** 2026-07-18 · hygiene: [[_Agent-Dream-Hygiene]] · run `py -3 tools/agent_dream.py`
<!-- AGENT_DREAM_FOOTER_END -->
