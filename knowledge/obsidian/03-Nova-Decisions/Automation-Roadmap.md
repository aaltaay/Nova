# Automation Roadmap

> **Canonical Nova OS progress:** see [[Nova-OS-Status]] and the mission canvas (`nova-os-mission.canvas.tsx`). This note is the historical A–F backbone; Nova OS phases P0–P10 extend it.

## Phase 0 — Memory (done)

- [x] Download course slide PDFs (Basics, SS101, Algo)
- [x] Ingest PDFs → Pinecone (`tools/course_memory/ingest.py`) — ~1080 vectors
- [x] Obsidian decision notes (this folder)
- [x] Active Strategy + backbone documented

## Phase A–F — Strategy backbone (done)

See [[Automation-Strategy-Backbone]] for detail.

- [x] **A** — Watchlist dashboard (`backend/strategy/watchlist.py`)
- [x] **B** — Setup trigger engine (Gap-and-Go, Bull Flag, ABCD)
- [x] **C** — Risk / discipline engine (`backend/strategy/risk.py`)
- [x] **D** — Paper execution via IBKR (`backend/strategy/executor.py`, binary arm)
- [x] **E** — Journal + go/no-go bar (`backend/journal/`)
- [x] **F** — Level 2 learning (record only; `backend/l2/`)

## Nova OS — phased plan (P0–P10, in progress)

| Phase | Focus | Status |
|-------|--------|--------|
| P0 | Baseline, status note, continuity rule, mission canvas, doc reconcile | **verified** |
| P1 | Event log, reason codes, loss-policy constants | next |
| P2 | `decide()` brain, API, stream wiring (signal only) | verified 2026-07-15 |
| P3 | DecisionPanel, CLI, notifications framework | pending |
| P4 | Confirm mode + emergency controls | pending |
| P5 | Auto paper + restart recovery | pending |
| P6–P9 | Archive capture, compaction, R2, replay, rewind | pending |
| P10 | Live-readiness review (GO/NO-GO only) | pending |

Full map: Nova OS plan in `.cursor/plans/` and [[Nova-OS-Decision-Brain]].

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

### Phase 3 — Tighten (ongoing via Nova OS P2–P10)

- [ ] Graduated control modes (not binary arm)
- [ ] Nova OS decide() with full gate audit
- [ ] Permanent archive + replay
- [ ] Live only after explicit P10 GO/NO-GO (requires `IBKR_LIVE_TRADING_CONFIRMED`)
