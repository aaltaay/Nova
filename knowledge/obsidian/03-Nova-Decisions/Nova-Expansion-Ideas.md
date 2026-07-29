# Nova Expansion Ideas (inspired by Jesse / LLM-driven research loops)

> **Purpose:** Durable idea bank for "how do we upgrade Nova's research + backtest + agent workflow" inspired by Saleh's Jesse MCP pattern (LLM + tools run studies end-to-end) -- but adapted to Nova's IBKR equities, HOD Momo, archive, and constitution.
>
> **Use:** When you ask about "Nova expansion / upgrades", pull this list first, pick items, then turn chosen ones into phase-style plans. **Not** auto-scheduled; items here are candidates, not commitments.
>
> **Hard invariants (still apply):** `auto_live` NO-GO; IBKR-only market data when discovery=ibkr; IB Gateway execution gate only; no secrets in repo/logs; PROBLEM_LOG after real fixes; single-market-data-feed coherence.

Created: 2026-07-28 (Kimi K3 + Jesse MCP video discussion).

---

## E1 -- HOD Strategy Lab (MVP)

**Idea**
A productized "lab" surface where HOD momentum strategies are explicit, versioned packs (config + optional filter code pointers), runnable against archived days (tape + L1 + enrichment from the 2026-07-28 capture remediation) with side-by-side compare vs baseline.

**Outcome**
You can ask: "How would variant X have done on 2026-07-17 vs current gates?" and get a reproducible comparison, not a gut feel.

**Benefit**
- Turns replay from an audit tool into a daily strategy-development loop.
- Speeds up tuning HOD filters without risking live behavior.
- Uses existing assets: `hod_momo_replay.py`, fixtures, `l1_ticks`, `enrichment_snapshots`.

**Main risks**
- Overfitting to a few famous days (needs robustness battery -- see E4).
- Scope creep toward full execution before Phase B/I evidence is complete (keep `auto_live` NO-GO).

---

## E2 -- Study Runner (declarative research jobs)

**Idea**
A single declarative job format (JSON/toml) describing: symbols/universe, date range, strategy pack, data fixture set, robustness battery, and gates. One command (or one agent task) runs the whole study and emits artifacts.

**Outcome**
One-line study: "Run baseline HOD 11/12 vs candidate on 5 archived sessions, Monte Carlo on trade order, produce report + task-log." Deterministic inputs, logged outputs.

**Benefit**
- Repeatable studies instead of ad-hoc notebook runs.
- Agents (or a future MCP client) can queue studies without bespoke Python each time.
- Aligns with task-log/CHANGELOG discipline (every study gets an artifact trail).

**Main risks**
- Job spec becoming a second DSL nobody maintains -- keep it thin over existing APIs first.

---

## E3 -- Robustness battery (anti-overfit gate)

**Idea**
A standard set of checks any strategy change must pass before being labeled `verified`: Monte Carlo on trade ordering, block bootstrap, session-split (premarket/RTH/AH) performance, drawdown ceilings, and explicit "do not ship" thresholds.

**Outcome**
A strategy is only "verified" when it survives shuffles/splits, not just one good day.

**Benefit**
- Filters out lucky-fit HOD tweaks.
- Gives you a hard, honest gate like Jesse's overfitting checks, tuned to day-trade microcap realities.

**Main risks**
- False sense of safety on thin samples -- pair with minimum-trade-count rules.

---

## E4 -- Robustness gate thresholds + study promotion rules

**Idea**
Codify promotion rules: minimum closed trades, max drawdown, minimum expectancy, per-session stability, and what evidence must land in PROBLEM_LOG/CHANGELOG when a strategy fails gate.

**Outcome**
Clear, mechanical criteria for "this variant is allowed into production config" vs "interesting but rejected."

**Benefit**
- Removes ambiguity from strategy iteration.
- Future agents inherit the same bar, not vibes.

**Main risks**
- Too-strict gates during low-sample regimes -- allow explicit `experimental` label with smaller bar but loud UI tagging.

---

## E5 -- Nova MCP (read-only + lab verbs first)

**Idea**
Expose Nova as an MCP server for AI clients: read archive status, list replay fixtures, run replay for a date, run backtest study (Phase E), read audit docs, fetch task-log summaries. Explicitly **no** order placement, no spend unlocks, no bypass of `backend/ibkr` gates.

**Outcome**
Tools like Claude/Cursor/Kimi can ask Nova for grounded facts and run studies the way Saleh's LLM drives Jesse -- but on your equity/HOD stack.

**Benefit**
- Makes Nova interoperable with the same "agent + tools" pattern as Jesse, without adopting crypto Jesse.
- Centralizes research verbs instead of scattered scripts.

**Main risks**
- Security surface: must be local-only, auth'd, and read/lab-scoped (align with `llm-trading-agent-security` skill).
- Order verbs stay out of scope until a separate, audited phase.

---

## E6 -- LLM strategy drafting (configs/filters only)

**Idea**
Allow agents to draft new strategy *packs* (JSON thresholds, optional pure-Python filter functions) that are validated by unit tests + fake-feed pipeline + replay parity before ever touching live evaluation.

**Outcome**
LLM can propose "try strategy 12 with tighter consolidation + RVOL floor X", produce a pack, prove it on fixtures, and only then hand it to you for review.

**Benefit**
- Faster exploration of HOD filter space.
- Keeps code generation constrained and test-gated (no freeform execution).

**Main risks**
- Hallucinated gates that backtest well but are fragile -- mitigated by E3/E4 batteries and human approval.

---

## E7 -- Frozen study datasets (checksummed bundles)

**Idea**
Named, versioned archive bundles (like the 2026-07-17 fixture) with manifests: tape, bars, l1_ticks, enrichment snapshots, production alerts. Studies always declare which bundle(s) they used.

**Outcome**
Any study result is reproducible byte-for-byte; "it worked on my data" goes away.

**Benefit**
- Research integrity for strategy comparisons over time.
- Enables CI to rerun canonical studies when code changes.

**Main risks**
- Storage growth -- pair with retention policy and R2 cold archive conventions.

---

## E8 -- Per-study report bundles

**Idea**
Every study emits a folder: metrics JSON, charts (optional), strategy pack hash, fixture IDs, gate results, links to task-log entry and PROBLEM_LOG anomalies.

**Outcome**
You can open one directory and understand a study months later without re-running it.

**Benefit**
- Durable memory for strategy decisions (why variant B lost to A).
- Feeds Reports v2 with richer provenance.

**Main risks**
- Chart generation dependencies -- keep optional and degrade to JSON-only in CI.

---

## E9 -- Paper/confirm graduated strategy trials

**Idea**
When a strategy pack passes lab gates, allow a **paper-only** trial mode with receipts and day logs, still under `confirm` / `auto_paper` rules -- never `auto_live`.

**Outcome**
Bridge between backtest and Phase B shadow: strategies earn paper evidence before any human considers live money.

**Benefit**
- Cleaner path to Phase B evidence for strategy changes, not just platform changes.

**Main risks**
- Confusing strategy-trial evidence with platform Phase I unlock -- separate ledgers.

---

## E10 -- Crypto-only Jesse sandbox (explicitly separate)

**Idea**
If you want hands-on with Saleh's exact workflow: run Jesse + Jesse MCP in a separate directory/env for crypto research. Nova code, HOD admission, and IBKR execution remain untouched.

**Outcome**
You can experiment with crypto LLM-driven backtests without contaminating Nova's equity/IBKR product.

**Benefit**
- Satisfies curiosity about the Jesse pattern with zero product risk to Nova.

**Main risks**
- Distraction from Nova roadmap; treat as weekend research only.

---

## E11 -- Third-party IBKR MCP (research-only)

**Idea**
Evaluate read-only IBKR MCP bridges (account/quote/context) as auxiliary research tools. Never let them place orders through Nova's execution path; treat as observability only.

**Outcome**
Optional extra context for agents; no execution authority.

**Benefit**
- Could speed portfolio/diagnostics Q&A in chat.

**Main risks**
- Overlap with existing `/api/ibkr/status` + specialists; only adopt if it clearly reduces toil.

---

## E12 -- Archive-informed alert triage copilot

**Idea**
Use archive + replay to answer "why did / didn't this alert fire?" with evidence (l1_ticks, enrichment snapshots, gate counters) -- a copilot over your own historical decision stream.

**Outcome**
Faster debugging of missed/false HOD alerts without spelunking logs.

**Benefit**
- Leverages the G1-G9 remediation data you just added.

**Main risks**
- UI scope; start as CLI/study runner verb before pretty panels.

---

## How to use this file

1. Ask for expansion -> open this list.
2. Pick 1-2 items; restate desired outcome.
3. Turn the chosen item into a plan with phases, tests, and logs per constitution.
4. Update this file when ideas are promoted, dropped, or re-scoped.

**Suggested first picks (highest leverage):** E1 (Strategy Lab MVP) + E3/E4 (robustness battery + gates), then E2 (Study Runner) once the lab works.
