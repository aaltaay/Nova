# 2026-09-06 -- Deep-dive audit parked as D-011..D-040

- **Status:** completed
- **Agents:** parent (Cursor cloud agent) + four read-only `explore` sub-audits (execution, IBKR feed, frontend UX, secondary areas)
- **Domain:** execution | market-feed | widgets | news | hod-momo | ibkr-ops | tester | security | docs
- **Related:** `CHANGELOG.md` 2026-09-06 · `DEFERRED_LOG.md` D-011..D-040 · `PROBLEM_LOG.md` n/a (nothing fixed) · Roadmap reliability WS1 (D-035)

## Task

Operator asked for a deep dive into every section of Nova for underdeveloped features, known-but-untracked bugs, and not-yet-found bugs -- with an explicit instruction **not** to change code, only to record the findings in the proper tracker (`DEFERRED_LOG.md`), focusing on reliability, speed, and execution.

## Goal

Every real gap found gets a `D-NNN` with Kind / Severity / Effort / Why parked / Blast radius / Unblock / Next / Evidence, so `py -3 tools/deferred_log.py status` becomes the honest to-do list and no future chat rediscovers the same problem.

## Why it mattered

Three kinds of drift had built up:

1. Gaps recorded only as CHANGELOG `Follow-ups:` bullets (261 of them) or as an `OPEN/DEFERRED` PROBLEM_LOG line (Jul 30 premarket) -- invisible to the ranked list.
2. Code that contradicts its own ADR (ADR 007 lock scope, ADR 010 thread purity, ADR 008 comments) with green tests, because the contradiction has no test.
3. UI honesty gaps where the backend already emits the truth (`feed_error`, `subscriptionError`, `table_state`) and the frontend never paints it.

## What we changed

- `DEFERRED_LOG.md`: 30 new open entries D-011..D-040 (1 P0, 14 P1, 14 P2, 1 P3) plus a batch banner under `OPEN_START`.
- `CHANGELOG.md`: one entry describing the batch.
- This task-log + `INDEX.md` row.
- No product code, tests, rules, or ADRs were changed.

## How it works now

Ranked by `deferred_log.py status`:

| Cluster | Entries | Shape |
|---|---|---|
| Spend safety | D-011 (P0), D-037, D-038, D-012 | `send_broker` runs after `_lock` exits (ADR 007 says inside); kill switch is skipped by `skip_risk` manual paths and is memory-only; live spend allowed with `broker_account_kind=unknown`; ledger writes + cancel-verify on the wrong thread |
| Desk honesty | D-021, D-022, D-023, D-014, D-013 | ticker WS never reconnects; scanner last-good rows with no marker and `subscriptionError` never painted; 11 status pollers keep last-good "connected"; sample orders on an empty blotter; order ticket drops FastAPI `detail` |
| IB loop speed | D-018, D-019, D-020, D-025, D-024, D-039 | hist SQLite inline on the IB loop; O(n) cache rebuild per tick; `listing_flags` 1.8 s sleep + off-owner `reqMktData`; short pacing sleeps; unbounded maps; reqIds surviving reconnect / no Error 101 budget |
| Enrichment / news | D-016, D-015, D-028 | yfinance failure negative-cached 15 min silently; Catalysts intersect IBKR roster only; FinBERT cold load on the 2-worker scan pool; Finnhub 429; HOD integrity mutual vouch |
| Persistence / infra | D-017, D-029, D-030, D-031, D-032, D-026, D-027 | schema_version gaps; CI runs neither lint nor Vitest (master ESLint-red); Railway leftovers + unrotated console log; frontend render/chunk/CSS size; Electron restart race; commit/broadcast split-brain; depth force-evict |
| Bookkeeping | D-033, D-034, D-035, D-036, D-040 | coverage holes; stale comments vs ADRs; Jul 30 premarket OPEN promoted; eight CHANGELOG follow-ups grouped; `/api/config` loopback write decision |

## Why this approach

- **Four parallel read-only sub-audits, then parent verification.** Breadth (backend feed, execution, frontend, secondary) is too wide for one context; but `verification-before-completion.mdc` forbids trusting a subagent report. Every P0/P1 claim was re-read in source by the parent before it became an entry (snippets and line ranges cited per entry). Two sub-audit claims were dropped after checking: the Gappers projection copying `change_pct` into `gap_percent` is the correct premarket definition (no open exists before 09:30), and `agent_contract.py` only fails locally because canvases live on a Windows-only path (`--ci` passes).
- **Fresh gates instead of memory.** pytest / Vitest / tsc / build / ESLint / ruff / maintainer / doc_invariants / agent_fleet / security_audit were all run this session; the ESLint-red-on-master finding (D-029) came from that, not from reading.
- **Grouped entries where the fix is one change.** Five memory leaks (D-024), six scanner honesty gaps (D-022), eight CHANGELOG follow-ups (D-036) share an entry each; splitting them into 20 entries would bury the P0. The rule says split when one is pulled.
- **Decisions marked as `decision`, not `bug`.** Kill-switch scope (D-037), depth eviction policy (D-027), loopback `.env` writes (D-040), sample orders default (D-014 Unblock) are product calls; recording them as bugs would invite a silent semantics change.
- **Rejected:** fixing the Effort-S items in the same session (operator said docs only); opening a new tracker document (DEFERRED_LOG already exists and has tooling); writing PROBLEM_LOG entries (nothing was fixed).

## Verification

- `pytest backend/ -q` -> 1481 passed (106 s)
- `npx vitest run` -> 858 passed / 177 files
- `npx tsc --noEmit` exit 0; `npm run build` exit 0 (App chunk 705 kB warning -> D-031)
- `npx eslint . --max-warnings=0` exit 1: 4 errors, 6 warnings (-> D-029)
- `python3 -m ruff check backend` -> 11 findings (-> D-029)
- `tools/maintainer_checks.py` FILE_SIZE / SWALLOWED_EXCEPTION rows folded into D-031 / D-016 / D-034
- `tools/doc_invariants.py` OK; `tools/agent_contract.py --ci` PASS; `tools/security_audit.py` 0 open findings
- `python3 tools/deferred_log.py status` lists 37 open (30 new); `pytest tools/test_deferred_log.py` 8 passed

## Follow-ups

All in `DEFERRED_LOG.md`. Pull order suggested in the batch banner: D-011 -> D-037/D-038 -> D-021/D-022/D-023/D-014. Do not start D-011 without the two-concurrent-SELL regression test named in its Next.

## Keywords

deep dive, audit, DEFERRED_LOG, D-011, ADR 007 lock, kill switch, broker_account_kind, useTickerStream reconnect, scanner honesty, useIbkrStatus, sample orders, hist sqlite IB loop, apply_l1_quote, listing_flags, schema_version, CI lint vitest, Railway leftovers, premarket 04:00
