# 2026-08-18 — Problem log pattern analysis: 236 entries categorized

- **Status:** completed (analysis; no product code changed)
- **Agents:** parent
- **Domain:** docs / ops
- **Related:** `PROBLEM_LOG.md` (all entries 2026-04-15 → 2026-08-18) · canvas `problem-log-analysis.canvas.tsx` · Nova-Roadmap-Status open item "premarket stack up before 04:00 ET" (2026-07-30 OPEN/DEFERRED)

## Task

User: "Every time I wake up and operate this tool, it doesn't work. Analyze all of our backlog problems and tell me what we can learn from categorizing them and making them all go away."

## Goal

Read every PROBLEM_LOG entry, categorize by primary cause, extract cross-cutting patterns, explain the recurring morning failure, and name systemic fixes (with honest shipped/partial/open status) that erase whole categories instead of individual symptoms.

## Why it mattered

The operator's lived experience is "broken every morning" despite ~236 logged fixes. Without pattern-level analysis, each morning incident gets a fresh spot patch and the class survives. This entry preserves the categorization so future sessions never re-read all 236 entries to re-derive it.

## What we changed

- No product code. Produced canvas `problem-log-analysis.canvas.tsx` (Cursor projects canvases folder) + this entry.
- Definitive counts: 236 dated entries (`^## \d{4}-\d{2}-\d{2}` via Select-String), 2026-04-15 → 2026-08-18. July = 184 (78%); Jul 13–24 alone = 141 (60%); Aug = 37; Apr = 14; May = 1.

## How it works now

**Category counts (primary cause, one per entry):** HOD Momo & scanner engine 38 · build/test/tooling 34 · IBKR session & morning bring-up 29 · UI layout/CSS 27 · silent failures & dishonest empties 26 · IB loop starvation & pacing 22 · frontend state races 19 · execution & order truth 16 · charts/historical 10 · deploy era (Railway, retired) 9 · observability noise 4 · security/misc 2.

**Five root patterns explain most of the log:**

1. **One shared lane for hot + cold work** (~35): IB socket + one loop carried L1 ticks, hist pulls, snapshots, completed-orders replay, sync SQLite. Cold bulk starved hot ticks → desk froze → false API_WEDGED → auto-heal killed live processes. Died by architecture: ADR 010 (dedicated IB loop, hot/cold scheduler), ADR 012 (store-first bars, pacing budget), archive write queue (2026-08-18).
2. **Errors dressed as empty data** (~30): `except → []`, sticky error strings, silent fallbacks. "No gappers yet" when the truth was "feed is down." Fixed in core (typed errors, last-good + stale flags, fail-loud rules) but recurs in each NEW module (afterhours 07-23, dominant-tab freeze 08-18) because the invariant is convention, not a test.
3. **Lifecycle state without owner/fence** (~30): zombie L1 subs across reconnects, session highs wiped on restart, id()-memoized frozen active set, sticky paper/live intent, stuck schema_version. Working fix shape: generation counters + epoch fencing (ADR 008) + persisted session state. Every new cache is a new risk.
4. **Two owners for one truth** (~25): Alpaca vs IBKR, positions() vs portfolio(), ledger vs ib.trades(), L1 vs hist candles, one-shot vs persistent scanners. Fix that stuck: one SSOT, delete/gate the other (single-market-data-feed rule, candle source column, ledger-first blotter).
5. **Verification scoped too small** (~15 recurrences): ib_async pin bump verified on orders → scanners silently empty (startReq removed); chart-fill verified on candles → Gainers L1 froze; HOD lag "fixed" 3x at render layer before the real cause (StrictMode double-socket duplicate alerts). Verify the loudest neighbor of the shared resource touched.

**The morning failure is a 5-leg chain, not one bug:** (A) session decays overnight — IBC 23:45 restart, sometimes as paper; Error 1100; weekly 2FA (08-16, 08-04, 07-31) — self-heal/follow-Gateway/sticky-intent-expiry shipped, 2FA still human. (B) cold-start thundering herd at first READY (07-29, 08-14 x2, 08-18) — ADR 010/012 + quiet window + write queue shipped. (C) misdiagnosis amplifies — false API_WEDGED auto-heal kills, wrong 2FA prereq copy (08-14, 08-17, 08-03) — fixed. (D) broken renders as calm — empty tables read as "no gaps" (07-14 origin, 07-20, 07-24) — loud banner + last-good shipped. (E) **OPEN umbrella:** nobody proves the stack is up before 04:00 ET unattended (07-30 OPEN/DEFERRED). Pieces exist (IBC AutoRestart, NovaDailyStart, health waits); missing: end-to-end unattended proof + one loud alert naming the failed leg.

**Recurrence hall of fame:** API_WEDGED 12 entries (Jul 16→Aug 18, died by architecture) · empty scanners 10 · "chart bars timed out" 9 ("the timeout was the wrong constraint") · HOD tab lag 4 (3 wrong fixes) · sticky integrity errors 5.

## Why this approach

Categorized by **primary cause** (not symptom or file) because the user asked what makes classes go away; symptom buckets would over-count the same root many times. Rejected: sampling (log small enough to read fully; sampling would miss the 3-correction chains), automated keyword clustering (titles lie -- several entries retract earlier entries), and treating each morning incident as one category (evidence shows 5 independent legs multiplied together). Presented in a canvas (data-heavy, tables + charts) with the durable conclusions here so the analysis survives outside chat history.

## Verification

- Entry count: `Select-String '^## \d{4}-\d{2}-\d{2}' PROBLEM_LOG.md | Measure-Object` → 236; per-date group sums re-added to 236 across categories and weeks.
- Full read of all entries in 4 chunked passes (no sampling).
- Canvas TypeScript check: no errors on write.

## Follow-ups

- **Highest leverage (answers the user's exact complaint):** ship the morning autopilot proof loop -- scheduled bring-up (IBC restart → NovaDailyStart → 03:55 ET self-check: Gateway READY, API READY, gapper rows > 0, loop lag OK) + one loud phone/Discord alert naming the failed leg. Roadmap already tracks it as the 07-30 deferred item; Phase D alert channels exist and are unused for this.
- Mechanical guards worth adding: maintainer check for sync I/O (sqlite3/open()) in IB-callback modules; clear-on-success regression template for every sticky error; conftest autouse tmp cache_dir + env pins (global test isolation); blast-radius line in verification checklist.

## Keywords

problem log, pattern analysis, morning failure, wake up broken, API_WEDGED, empty gappers, silent failure, event loop starvation, SSOT, categorization, morning autopilot, pre-market 04:00, unattended startup
