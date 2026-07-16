# Graph Report - knowledge\obsidian  (2026-07-16)

## Corpus Check
- 29 files · ~17,955 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 249 nodes · 249 edges · 21 communities
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `89712d5a`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Strategy Automation & Safety
- Course Memory & Library
- Nova OS Phases & Readiness
- Warrior Trading Courses
- Active Strategy Selection
- Market Data Providers
- Community 6
- Community 7
- Community 8
- Scanner Data Provider — IBKR primary (no Alpaca SIP)
- Catalog
- What TraderVue shows (reports that matter)
- Automation Roadmap
- Five Pillars + Gap and Go — Technical Spec (implemented)
- Local Market Data Recorders
- Productization Decision (Phase J)
- IBKR: live market data, orders locked by default
- News Impact Decision Layer
- Nova OS Archive Restore Runbook
- Decision: One Warrior Trading library under `downloads/`
- Candidate Strategies for Nova

## God Nodes (most connected - your core abstractions)
1. `Phase ledger` - 13 edges
2. `Nova OS Status` - 10 edges
3. `Scanner Data Provider — IBKR primary (no Alpaca SIP)` - 10 edges
4. `Nova Automation Strategy — Backbone` - 9 edges
5. `Nova OS — AI decision layer (buy / no-buy)` - 9 edges
6. `Checklist (must all be green before any future GO)` - 9 edges
7. `Alpaca Integration Reference` - 8 edges
8. `Decision pipeline (ordered gates)` - 8 edges
9. `Nova Roadmap Status` - 8 edges
10. `How Recall Works (Pinecone + Obsidian)` - 7 edges

## Surprising Connections (you probably didn't know these)
- None detected - all connections are within the same source files.

## Communities (21 total, 0 thin omitted)

### Community 0 - "Strategy Automation & Safety"
Cohesion: 0.10
Nodes (15): Active Strategy (Nova), Chosen strategy, Explicit non-goals, Mechanical rules (must be codeable), Nova mapping, Completed this phase, Crash or blocker, Current position (+7 more)

### Community 1 - "Course Memory & Library"
Cohesion: 0.09
Nodes (17): Course Index, Day Trading: The Basics — videos on disk, LMS inventory, Timestamped transcripts (match the video), BA101 Transcript Index, DE101 Transcript Index, Canonical roots (do not duplicate under `docs/`), Free / member resource pages → `warrior-trading-resources/` (+9 more)

### Community 2 - "Nova OS Phases & Readiness"
Cohesion: 0.10
Nodes (16): Commands (from repo root), Graphify Knowledge Graph, How this fits the memory router, Install / skill locations, Where it lives, Accuracy model (important), Commands, How Recall Works (Pinecone + Obsidian) (+8 more)

### Community 3 - "Warrior Trading Courses"
Cohesion: 0.10
Nodes (20): COMPLETE history (do not reopen), Crash or blocker, Current position, Exact next action (human), Governance — `[x]` COMPLETED, History (append-only), Nova Roadmap Status, Phase A — Skills library — `[x]` COMPLETED (+12 more)

### Community 4 - "Active Strategy Selection"
Cohesion: 0.12
Nodes (16): Decision pipeline (ordered gates), Gate 0 — Session / regime (hard), Gate 1 — Five Pillars (hard, already coded), Gate 2 — Setup recognition (hard for Gap-and-Go), Gate 3 — Ticket math (hard), Gate 4 — Catalyst / quality (soft → human or LLM assist), Gate 5 — Microstructure (soft until proven), Gate 6 — Execution policy (+8 more)

### Community 5 - "Market Data Providers"
Cohesion: 0.13
Nodes (14): (A) Already IBKR-native — safe today, Alpaca Integration Reference, API endpoints (`main.py` — no separate `routes/settings.py`), (B) IBKR-partial, `backend/constants.py`, (C) Alpaca-only — no IBKR alternative exists, Classification key, Config surface (entirely Alpaca-shaped today) (+6 more)

### Community 6 - "Community 6"
Cohesion: 0.13
Nodes (15): Adherence, Archive integrity, Checklist (must all be green before any future GO), Control-mode confirmation, Emergency drills, Expectancy, Next action, **NO-GO for `auto_live`** (+7 more)

### Community 7 - "Community 7"
Cohesion: 0.14
Nodes (14): 0. Honest framing (read first), 1. The edge, in one paragraph, 2. What we CAN automate (high confidence), 3. What we should NOT (yet) automate, 4. Why this fits Nova specifically, 5. Phased plan (no money at risk early), 6. Open decisions (fill as we go), 7. Decision log (append-only) (+6 more)

### Community 8 - "Community 8"
Cohesion: 0.17
Nodes (12): backtest, backtesting-frameworks, How agents should load these, Intentionally not vendored, llm-trading-agent-security, Nova guardrails (applies to every skill below), optimize, Related project skills (pre-existing) (+4 more)

### Community 9 - "Scanner Data Provider — IBKR primary (no Alpaca SIP)"
Cohesion: 0.18
Nodes (10): Decision, IBKR subscriptions required for this path, Implementation (2026-07-13), Related, Risks / gaps to validate before flipping the flag, Scanner Data Provider — IBKR primary (no Alpaca SIP), Soft-toggle (do not destroy Alpaca), Undo (+2 more)

### Community 10 - "Catalog"
Cohesion: 0.20
Nodes (10): awesome-cursor-skills, Catalog, deltalytix, nautilus_trader, Reference Repos (study catalog), Related Nova notes, Study-vs-dependency boundary, TradeNote (+2 more)

### Community 11 - "What TraderVue shows (reports that matter)"
Cohesion: 0.22
Nodes (8): Calendar (critical), Explicit non-goals (v1), Other Overview modes, Report sub-tabs (growth / analytics), Skipped for Nova, TraderVue Reporting Parity (Nova), What Nova will mirror (v1), What TraderVue shows (reports that matter)

### Community 12 - "Automation Roadmap"
Cohesion: 0.25
Nodes (8): Automation Roadmap, Legacy phase labels (superseded by Nova OS map), Nova OS — phased plan (P0–P10), Phase 0 — Memory (done), Phase 1 — Signal only (superseded by A–B + future P2), Phase 2 — Paper execution (superseded by D + future P4–P5), Phase 3 — Tighten (Nova OS P2–P10), Phase A–F — Strategy backbone (done)

### Community 13 - "Five Pillars + Gap and Go — Technical Spec (implemented)"
Cohesion: 0.29
Nodes (6): 1. Five Pillars scoring (`backend/strategy/five_pillars.py`), 2. Gap and Go setup (`backend/strategy/gap_and_go.py`), 3. Read-only API (`backend/routes/strategy.py`), 4. Tests (mock data, no network, no broker calls), 5. UI transparency principle (applies to every future control), Five Pillars + Gap and Go — Technical Spec (implemented)

### Community 14 - "Local Market Data Recorders"
Cohesion: 0.29
Nodes (7): Deferred, Future backtest / relearn read path, Goal, How to recall “L2 at second T”, Local Market Data Recorders, Storage choice: SQLite (WAL) + batched inserts, What gets recorded

### Community 15 - "Productization Decision (Phase J)"
Cohesion: 0.29
Nodes (7): Exit (Phase J), Productization Decision (Phase J), Recommendation, Revisit triggers, What SaaS would require (explicitly deferred), What stays local, Why

### Community 16 - "IBKR: live market data, orders locked by default"
Cohesion: 0.33
Nodes (5): Current user .env (2026-07-13), IBKR: live market data, orders locked by default, Paper trading (when ready), Policy (single source of truth), Situation

### Community 17 - "News Impact Decision Layer"
Cohesion: 0.33
Nodes (5): Impact classes (plain English), News Impact Decision Layer, Visible factors, What already existed, What this layer adds

### Community 18 - "Nova OS Archive Restore Runbook"
Cohesion: 0.33
Nodes (6): Goal, Local restore drill, Nova OS Archive Restore Runbook, R2 restore (when keys configured), Replay after restore, Trim / purge

### Community 19 - "Decision: One Warrior Trading library under `downloads/`"
Cohesion: 0.33
Nodes (5): Agent rule, Decision, Decision: One Warrior Trading library under `downloads/`, What we do instead, Why

### Community 20 - "Candidate Strategies for Nova"
Cohesion: 0.40
Nodes (4): Candidate Strategies for Nova, Candidates (fill after first Pinecone queries), Evaluation criteria (automation-friendly), Working recommendation (update after study)

## Knowledge Gaps
- **181 isolated node(s):** `Where it lives`, `How this fits the memory router`, `Commands (from repo root)`, `Install / skill locations`, `Accuracy model (important)` (+176 more)
  These have ≤1 connection - possible missing edges or undocumented components.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Nova Roadmap Status` connect `Warrior Trading Courses` to `Strategy Automation & Safety`?**
  _High betweenness centrality (0.074) - this node is a cross-community bridge._
- **Why does `Nova OS — AI decision layer (buy / no-buy)` connect `Active Strategy Selection` to `Strategy Automation & Safety`?**
  _High betweenness centrality (0.061) - this node is a cross-community bridge._
- **Why does `Nova OS Live-Readiness Review (P10)` connect `Community 6` to `Strategy Automation & Safety`?**
  _High betweenness centrality (0.057) - this node is a cross-community bridge._
- **What connects `Where it lives`, `How this fits the memory router`, `Commands (from repo root)` to the rest of the system?**
  _181 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Strategy Automation & Safety` be split into smaller, more focused modules?**
  _Cohesion score 0.10333333333333333 - nodes in this community are weakly interconnected._
- **Should `Course Memory & Library` be split into smaller, more focused modules?**
  _Cohesion score 0.08695652173913043 - nodes in this community are weakly interconnected._
- **Should `Nova OS Phases & Readiness` be split into smaller, more focused modules?**
  _Cohesion score 0.10476190476190476 - nodes in this community are weakly interconnected._