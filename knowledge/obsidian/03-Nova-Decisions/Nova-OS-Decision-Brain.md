---
title: Nova OS — decision brain for buy / no-buy
date: 2026-07-14
status: draft
tags: [nova-os, automation, gap-and-go, ibkr]
---

# Nova OS — AI decision layer (buy / no-buy)

> Companion to [[Automation-Strategy-Backbone]], [[Five-Pillars-and-Gap-and-Go-Spec]], [[Active-Strategy]], [[Nova-OS-Status]].  
> **Nova OS** = the rule + judgment brain. **IBKR module** = broker hands. **Scanner / L2 / news** = senses.  
> **Status across chats:** [[Nova-OS-Status]] is canonical; mission canvas is the visual board.

## Implementation status (2026-07-15)

- **Backbone A–F shipped:** watchlist, setups, risk, journal/go-no-go, IBKR paper executor (binary arm), L2/tape local recorders.
- **Nova OS P0–P2 verified:** continuity artifacts; append-only event log + vocabulary; `decide()` gate pipeline (signal only) + decide API + stream wiring. See [[Nova-OS-Status]].
- **Not yet built:** DecisionPanel / control-mode ladder / confirm queue (P3–P5), permanent archive (P6–P9), live-readiness review (P10).

## Honest framing

Nova OS does **not** guarantee profitable trades. It guarantees **discipline**: only trade when coded rules + risk caps pass; otherwise output **NO BUY** with a reason. Live money stays behind `IBKR_ENABLED` + `IBKR_LIVE_TRADING_CONFIRMED` (see constitution).

## Stack (what is what)

| Layer | What it is today | Role |
|-------|------------------|------|
| **Senses** | IBKR discovery/reprice, L2, tape, news impact, yfinance float | Facts about symbols |
| **Nova OS (brain)** | Five Pillars + Gap-and-Go (signal-only) + reference memory (Pinecone/Obsidian) + future risk state machine | **BUY / NO BUY / WAIT** + ticket fields |
| **Hands** | `backend/ibkr/` orders + safety gates | Paper/live execution when allowed |
| **CLI / UI** | Trading tab, strategy APIs, optional future CLI | Same brain, different shell — **not** a second broker |

There is **no Ruby wrapper** in this repo. Broker access is **Python** (`ib_async` / Gateway). A CLI would just call the same Nova OS APIs the UI uses.

## Decision pipeline (ordered gates)

Every candidate must pass **in order**. Fail → **NO BUY** + reason code. Soft checks may produce **WAIT** or **BUY_SMALL** (paper / reduced size).

### Gate 0 — Session / regime (hard)

- Market session allows trading (RTH for Gap-and-Go default window).
- Daily max loss not hit; walk-away flags clear (after first loss / giveback / N losses — from backbone).
- Bot mode: `signal` | `paper` | `live` (live requires explicit env confirm).

### Gate 1 — Five Pillars (hard, already coded)

All five must pass (`backend/strategy/five_pillars.py`):

1. Price $2–$20  
2. % change ≥10%  
3. RVOL ≥5×  
4. Catalyst (news flag or explicit technical override)  
5. Float ≤20M  

Missing data = **fail closed**.

### Gate 2 — Setup recognition (hard for Gap-and-Go)

Default setup (direction set in backbone): **Gap and Go**

- Time: 9:30–10:00 ET  
- Premarket high marked; trigger = break of PM high (see `gap_and_go.py`)  
- Prefer obvious flat-top / flag; watchlist 2–4 names only  
- Entry requirements: early volume (e.g. ≥100k first minute), pattern clear, **≥2:1** achievable  

Other setups (Bull Flag, ABCD) = later modules; do not mix into one blob.

### Gate 3 — Ticket math (hard)

Before any BUY:

- `entry`, `stop`, `target` computed  
- Risk per share = entry − stop; target ≥ entry + risk × **2**  
- Share size from account risk budget + daily state (¼ size until cushion — backbone)  
- Stop preferably tight (5–10¢; **20¢ max** on scalps per backbone)

If ticket invalid → **NO BUY**.

### Gate 4 — Catalyst / quality (soft → human or LLM assist)

- Prefer breaking / quality news; unconfirmed = caution  
- LLM may **triage** headlines; must not alone authorize full size (backbone §3)  
- Output: `catalyst_confidence` + notes for journal  

### Gate 5 — Microstructure (soft until proven)

- L2 / T&S: heavy ask resistance, buying drying up → **WAIT** or exit rules later  
- Until L2 path is trusted: do **not** auto-enter on tape nuance alone; signal-only or human confirm  

### Gate 6 — Execution policy

| Mode | Action |
|------|--------|
| Signal | Emit checklist + ticket; `would_execute=False` (current Gap-and-Go API) |
| Paper | IBKR paper bracket (entry + stop + target) via `ibkr/` |
| Live | Same, only after paper metrics bar + live flags |

**Exit automation (when enabled):** scale half at first target → stop to BE; bail on heavy L2 sell / T&S sell flood; 5-min first red candle if entry was 5-min-based (playbook exit indicators). Until then: human manages exits or simple bracket only.

## What Nova OS should output

```text
decision: BUY | NO_BUY | WAIT
reason_codes: [PILLAR_FLOAT_FAIL, ...]
setup: gap_and_go
symbol: XYZ
ticket: { entry, stop, target, shares, risk_dollars, r_multiple }
confidence: 0–1
mode: signal | paper | live
citations: [reference chunk ids / pillar scores]
```

## Rules we feed Nova OS (summary checklist)

1. Only Five-Pillars A+ names.  
2. Only defined setups in the time window.  
3. Always know max loss and target before entry.  
4. Min 2:1 R; never revenge-size; walk away after loss rules.  
5. Process over P&L; journal every decision.  
6. Cap losers; scale winners; no averaging into broken thesis.  
7. Prefer most-watched gapper (crowd), not obscure names.  
8. Paper until expectancy + adherence metrics clear the bar.

## Open decisions

- Finalize [[Active-Strategy]] (Gap and Go first vs multi-setup).  
- CLI: optional thin client over `/api/strategy/*` + future `/api/nova-os/decide`.  
- When to promote Gate 5 (L2) from soft to hard.

## Related

- [[Nova-OS-Status]] — canonical phase, verification ledger, next step
- [[Automation-Strategy-Backbone]]  
- [[Automation-Roadmap]]  
- [[Local-Market-Data-Recorders]] — hot SQLite recorders; archive phases P6–P9 extend this
- [[IBKR-Orders-Locked-On-Live-Gateway]]  
- [[Scanner-Provider-IBKR-Primary]]
