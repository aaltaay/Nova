# Deferred log (agent-maintained -- MANDATORY)

This file is the **shared parking lot for work we already know about and did not do**. Known bugs found mid-task. Features the human asked for that got parked because they are too big, need an ADR, or were the wrong job for that session.

**Mandatory for every agent** in this project (parent sessions and all Nova specialists). Rule: `.cursor/rules/deferred-log.mdc`. Finding a real bug (or parking a real feature) and walking away with no entry here is a constitution violation -- same severity as skipping `PROBLEM_LOG.md` after a real fix. Lifecycle footers must declare `deferred_log=<D-NNN>|none|skipped|n/a`.

This is **not** `PROBLEM_LOG.md` (that is closed: symptom / cause / fix). This is **not** `Nova-Roadmap-Status.md` (that is product NEXT / phases L-Z). This is **not** an agent-memory Backlog (those are specialist scratchpads; they are not the SSOT).

Ranked list without reading the whole file:

```text
py -3 tools/deferred_log.py status
py -3 tools/deferred_log.py next-id
```

Every new chat also sees open P0/P1 items in the session-start fleet brief.

## How to triage (so a human can decide)

| Field | What it answers |
|-------|-----------------|
| **Kind** | `bug` (wrong today) / `feature` (wanted, not built) / `decision` (blocked on a human call) |
| **Severity** | `P0` desk-broken, wrong money, trading safety, cannot operate. `P1` daily-use wrong (a column, a number, a control the operator uses every session). `P2` edge session / annoying / honesty gap that is not silent-wrong-money. `P3` polish. |
| **Effort** | `S` hours in one session. `M` a full session, shape is known. `L` architectural / multi-session / needs an ADR. |
| **Why parked** | Doing other work / too big for this task / needs an ADR / blocked on a human decision. Never "didn't feel like it." |
| **Blast radius** | What else is lying or missing while this stays open. |
| **Unblock** | The one decision or missing piece that lets an agent start. |
| **Next** | One concrete first step, not a design essay. |
| **Evidence** | How we know it is real (endpoint, screenshot, log line). No entry without this. |

Pull into a session when: severity is P0, or the human names the ID, or you are already in that module and Effort is S. Do **not** silently expand the current task into an L item -- write it here and finish what you were asked.

## How agents update this file

1. **When:** You found a real bug and did not fix it this session; or the human asked for a feature you parked; or you fully diagnosed a root cause and deferred the patch. Search this file first -- extend an existing ID rather than duplicating.
2. **Where (open):** Prepend a new `## D-NNN` section **immediately below** the `<!-- OPEN_START -->` marker. IDs are durable. Get the next one with `py -3 tools/deferred_log.py next-id`. Never reuse an ID.
3. **Where (done):** Cut the whole `##` section from Open into Closed (below `<!-- CLOSED_START -->`), set **Status:** `done`, add **Closed:** date plus **Related:** PROBLEM_LOG / CHANGELOG / task-log. Do not delete history.
4. **Keep it short:** A few lines per field. No secrets, tokens, or personal data.

Entry template (copy and fill in):

```markdown
## D-NNN -- Short descriptive title

- **Status:** open
- **Kind:** bug | feature | decision
- **Severity:** P0 | P1 | P2 | P3
- **Effort:** S | M | L
- **Domain:** market-feed | news | execution | hod-momo | ...
- **User-visible:** yes | no
- **Logged:** YYYY-MM-DD
- **Why parked:** One or two sentences. Name the task you were in.
- **Blast radius:** What else is wrong or missing while this stays open.
- **Unblock:** The decision or missing piece that lets an agent start.
- **Next:** One concrete first step.
- **Evidence:** Endpoint, log line, or screenshot that proves it.
- **Keywords:** comma, separated, terms, for, search
```

**Status values:** `open` (actionable) | `blocked` (waiting on Unblock) | `parked` (explicitly not this month) | `wontfix` (human said no) | `done` (belongs in Closed).

<!-- OPEN_START -->

## D-009 -- Ticker cold snapshot returns empty for a symbol chart bars fetch fine

- **Status:** open
- **Kind:** bug
- **Severity:** P2
- **Effort:** M
- **Domain:** market-feed
- **User-visible:** yes (Stock View / ticker detail can show an empty quote for a symbol that is trading fine)
- **Logged:** 2026-08-31
- **Why parked:** Found while diagnosing the XAIR "not on Gappers" report. The scanner-side L1 starvation (separate root cause) was fixed and verified this session; this ticker-detail cold-snapshot path is a different code path (`ticker_ibkr.py`) that this session did not trace to a root cause.
- **Blast radius:** `GET /api/ticker/{symbol}` can return `snapshot: {}` (and `avg_volume`/`rel_volume: None`) for a symbol whose 1Min bars are fetching correctly via `reqHistoricalData` (5 fresh bars, real volume) at the same moment. `ticker_ibkr._price_from_l1_stream` and `_price_from_chart_bars` both apparently returned `None` too, since the code fell through to the slow `snapshot_quotes` cold path, which then failed with a blank exception message (`ticker IBKR snapshot failed for XAIR: `).
- **Unblock:** Reproduce on a currently-live symbol with the same shape (has bars, no scanner L1 owner yet) and add a non-blank exception message/traceback at the `logger.warning` call in `ticker_ibkr.py` (currently logs `%s` on an exception whose `str()` is empty) so the actual IB error surfaces.
- **Next:** Read `ticker_ibkr.py` around the cold `snapshot_quotes` fallback (roughly lines 110-150), reproduce with a symbol not in any active L1 pool, and get a non-empty exception detail before deciding whether the fix belongs in `ibkr/discovery.snapshot_quotes` or the fallback ordering in `ticker_ibkr.py`.
- **Evidence:** `backend/logs/api-console.log` 2026-08-31 08:06:03 -- `WARNING ticker_ibkr ticker IBKR snapshot failed for XAIR: ` (empty message) immediately followed by `WARNING ticker_detail ticker REST: IBKR snapshot empty for XAIR - returning empty (no Alpaca fallback)`. Same minute, `GET /api/ticker/XAIR/bars?timeframe=1Min` returned 5 real bars (`c=5.7, v=302768` on the last one). `GET /api/ticker/XAIR` returned `{"snapshot": {}, "avg_volume": null, "rel_volume": null, ...}`.
- **Keywords:** ticker_ibkr, snapshot_quotes, cold snapshot, empty exception, XAIR, Stock View, blank error message

## D-008 -- Earnings-day-offset test fails; sentiment model import segfaults full suite

- **Status:** open
- **Kind:** bug
- **Severity:** P2
- **Effort:** S
- **Domain:** news
- **User-visible:** no (test-suite only; not touched by the IBKR session-watchdog work in this session)
- **Why parked:** Found while running the full backend suite to verify an unrelated IBKR fix (session freeze / watchdog). Both symptoms are in `backend/news/` and `backend/mover_evaluate.py`, neither of which this session touched -- wrong task to fix mid-verification.
- **Blast radius:** (1) `test_mover_columns.py::test_decorate_rows_attaches_earnings_window` fails deterministically -- `out[0]["earnings_day_offset"]` is `None` instead of `0` for a same-day earnings row. (2) `test_news_impact.py::test_fresh_bucket_boundary` triggers a native crash (`Windows fatal exception: code 0xc0000139`) while importing `torchvision`/`transformers` for the sentiment pipeline (`news/sentiment.py:_get_pipeline` -> `news/impact_evaluate.py:evaluate_news_impact`); pytest survives and the run completes, but that test's own pass/fail is unreliable on this machine.
- **Unblock:** (1) Read `mover_evaluate.decorate_rows`'s earnings-day-offset calc against the `2026-08-27` fixture case to find why 0-day offset resolves to `None`. (2) Pin/repair the local torch/torchvision/transformers install (DLL version mismatch is the classic cause of `0xc0000139`) or lazy-guard the sentiment pipeline import so a broken native extension degrades to no-sentiment instead of crashing the process.
- **Next:** Reproduce each in isolation (`py -3 -m pytest backend/tests/test_mover_columns.py::test_decorate_rows_attaches_earnings_window -q` and the news_impact test alone) and decide whether the torch crash needs a `try/except` import guard in `news/sentiment.py` or a local env fix.
- **Evidence:** `py -3 -m pytest -q` from `backend/`, 2026-08-31 -- 1446 passed, 1 failed (`test_mover_columns.py`), plus the printed native traceback during `test_news_impact.py::test_fresh_bucket_boundary`. Neither `backend/news/`, `backend/mover_evaluate.py`, nor their tests were modified this session (`git status --porcelain` on those paths is empty).
- **Update (2026-08-31, later session, XAIR L1-starvation fix):** Reconfirmed independently. `test_decorate_rows_attaches_earnings_window` passes every time run alone or as the only test in its file, but fails deterministically inside the full-suite run (order-dependent state leak, not a torch/transformers crash this time -- `1456 passed, 1 failed` with no native traceback). Confirmed it fails identically with this session's `hod_momo_active.py` / `scanner_hydrate.py` / `integrity_live.py` changes stashed out, so it is pre-existing test-isolation, not caused by either session's product code. Likely culprit: some earlier test in suite order mutates a module-global (`_fundamentals_cache`, or a memoized earnings/day-offset calc) that `mover_evaluate.decorate_rows` reads without a per-test reset.

## D-007 -- After-hours VWAP: Nova freezes at 16:00; Webull/DAS reset

- **Status:** parked
- **Kind:** decision
- **Severity:** P2
- **Effort:** M
- **Domain:** market-feed
- **User-visible:** yes
- **Logged:** 2026-08-28
- **Why parked:** Operator asked to record the platform mismatch and not change paint until the after-close consequences are clear. Premarket-in-the-same-line (04:00-16:00) already shipped this morning.
- **Blast radius:** After 16:00 Nova carries the 16:00 VWAP flat. Webull and DAS treat after-hours as a **new** VWAP (reset at 16:00), not more volume on the daytime line. TradingView with Extended Hours on keeps adding. A Webull vs Nova compare after the close will disagree. Overnight leftover still must not diagonal into tomorrow.
- **Unblock:** One live look -- Webull 1Min after 16:00: does the orange line sit still, start a new line, or keep walking? Do not flip `CHART_VWAP_SESSION_END_SEC` or add a second series without that.
- **Next:** After the cash close, screenshot Nova and Webull on the same symbol. Then either leave freeze (current), add a second AH VWAP (Webull/DAS), or keep adding (TradingView ETH).
- **Evidence:** TradingView help: VWAP "begins at the open and stops at the close" (ETH-on includes those bars). DAS docs: checkbox "also draw a VWAP line for pre and post" -- extra lines, not one blend. Community [Webull-Style Segmented VWAP](https://www.tradingview.com/script/E7GAlJYk-Webull-Style-Segmented-VWAP/) resets at premarket / regular / after-hours. Robinhood docs never state session bounds. Reddit r/Daytrading: IB / Webull / Fidelity / NinjaTrader printed different VWAPs the same morning.
- **Keywords:** VWAP, after-hours, 16:00, Webull, DAS, TradingView, session reset, CHART_VWAP_SESSION_END_SEC, D-007

## D-006 -- init_sentry + cache restore block HTTP yield for ~94s

- **Status:** open
- **Kind:** bug
- **Severity:** P1
- **Effort:** S
- **Domain:** ibkr-ops
- **User-visible:** yes
- **Logged:** 2026-08-28
- **Why parked:** Found on the 08:22 daily start soak. Patch is `app_lifespan.py` (move `init_sentry` / heavy restore after `yield` or bound it). The live API is `reload=true`; a backend edit would WatchFiles-restart it and, after 09:30, today's Gappers cannot be rebuilt.
- **Blast radius:** Daily start's old 60s health wait declared the API dead while the process was still in lifespan. UI shows API down / Start API. A click then kills a live PID.
- **Unblock:** After a no-reload API start (tomorrow's daily, or a weekend restart), defer `init_sentry` until after `yield` and time `_restore_caches` / `_init_databases`.
- **Next:** Add a lifespan test that `yield` happens before Sentry/network, then restart API with `NOVA_API_RELOAD=0`.
- **Evidence:** `api-console.log` 08:22:25 `instance starting` -> 08:23:32 Sentry enabled -> 08:23:59 `HTTP ready`. `daily-start.log` 08:23:05 `API health still failing after 60s`. Soak health later missed 4s then answered in 3689ms; `http_loop_lag_ms.max_ms` reached 4360.
- **Keywords:** init_sentry, lifespan yield, HTTP ready, HealthWaitSec, daily-start, API_WEDGED, Start API

## D-005 -- Aborted API terminal can leave a live process with no HTTP listener

- **Status:** open
- **Kind:** bug
- **Severity:** P1
- **Effort:** M
- **Domain:** ibkr-ops
- **User-visible:** yes
- **Logged:** 2026-08-26
- **Why parked:** Found while completing chart-tool verification; process supervision and safe stale-owner recovery are outside the chart UI task.
- **Blast radius:** Nova can show "Start API" while port 8000 refuses connections, but `run_api.py` refuses recovery because the lock owner PID is still active. The desk remains down until the orphan is identified and stopped.
- **Unblock:** Define a safe ownership rule that distinguishes a healthy active API from an orphaned, non-listening child without ever starting a second clientId 17 session.
- **Next:** Reproduce terminal abort in an isolated paper session, then make the launcher terminate its child on parent loss or add a listener/parent-aware stale-owner recovery after a bounded grace period.
- **Evidence:** Terminal 336841 was aborted at 21:52:45 ET; child `python3.13.exe` PID 35140 remained active through 22:01 with no port 8000 listener. A new start was rejected by `api-instance.lock`. Stopping the orphan and launcher, then starting once, restored `/api/health=connected`, IBKR `session=ready`, and 21 Gappers.
- **Keywords:** api-instance.lock, orphan API, terminal aborted, port 8000 refused, clientId 17, run_api.py, process supervision

## D-004 -- Vite restart-lock test shares the live lock path

- **Status:** open
- **Kind:** bug
- **Severity:** P2
- **Effort:** S
- **Domain:** frontend tooling
- **User-visible:** no
- **Logged:** 2026-08-26
- **Why parked:** Found while verifying the chart drawing task; changing API restart locking is unrelated to chart tools and needs its own focused test pass.
- **Blast radius:** `npx vitest run` can fail when a live Vite restart owns `backend/.cache/start-api.lock`, and the test's `afterEach` can delete that live lock, briefly removing restart-race protection.
- **Unblock:** None.
- **Next:** Make `acquireLock` / `releaseLock` accept an injected lock path or construct a lock owner around a path, then point the test at `tmpdir()` instead of the operator cache.
- **Evidence:** Full Vitest run at 21:57 ET failed `vite-nova-start-api.test.ts` because its first `acquireLock()` returned false while the running app held the production path; the test cleanup removed the lock and an immediate retry passed all 835 tests.
- **Keywords:** vite-nova-start-api, start-api.lock, test isolation, operator cache, restart race

## D-003 -- Trader 10Sec / Full Day sit on "Loading IBKR historical..." for minutes

- **Status:** blocked
- **Kind:** bug
- **Severity:** P1
- **Effort:** M
- **Domain:** market-feed
- **User-visible:** yes
- **Logged:** 2026-08-26
- **Why parked:** Phases 0-4 of the roadmap are implemented and pytest-green (fresh full-suite run, 1386 passed), but the running Nova API process could not be restarted from this agent session to live-verify (see Unblock) -- the process is not visible to this shell's `Get-Process` (likely a different Windows session/Electron sidecar), and the constitution forbids touching a live-trading process blindly. Do not close until a live restart confirms the pacing bucket and 10Sec paint time.
- **Blast radius:** Unchanged from the original diagnosis until live-verified: any ticker whose 10Sec/1Day series is not already in `bars_store` opens two black quadrants; Large Cap backfill competed for the same 60 req / 10 min IB bucket; stale 1Min/5Min took `open_chart` slots.
- **Unblock:** User restarts Nova (Desktop app relaunch, or the header "Start API" control, or `Run Nova.bat`) so the new code loads, then re-run the live checks in Next.
- **Next:** After restart, verify in the same session: (1) `/api/metrics/ops` -> `historical_pacing.window_used` stays well under 60 across two Large Cap roster commits (Phase 1). (2) Open a cold Trader symbol and confirm 10Sec paints within a few seconds via `/api/ticker/{symbol}/bars?timeframe=10Sec` (`bars` non-empty even before the hist fill lands) (Phases 2-4). (3) Re-check scanner L1 freshness (`/ws/scanner` patches or `/api/movers` ages) in the same window (blast-radius rule). Then move this entry to Closed and write the matching PROBLEM_LOG close-out.
- **Evidence (soak, 2026-08-26 ~19:32 ET):** Trader MSS: 5Min and 1Min painted; 10Sec and Full Day overlay. `/api/ticker/MSS/bars`: 10Sec n=0 filling=true; 1Day n=0 filling=true. `/api/metrics/ops` `ibkr.historical_bars` last_sample_age ~448s (no send for ~7.5 min). `backend/logs/blast.log` 18:53 shed storm of Large Cap 1Day (ORCL/T/F/PLTR/...).
- **Evidence (implementation, 2026-08-26 ~20:xx):** New `HistoricalPacing.snapshot()` unit-tested (`window_used` counts sends). `large_cap_hooks`/`large_cap_metrics` once-per-session + store-complete guards unit-tested (17 tests). `chart_bars.fetch_chart_bars` priority split (`open_chart` empty-store / `warm` stale-store / `background` unchanged for scan callers) unit-tested (36 tests). New `ibkr/tape_10sec.py` provisional 10Sec candles from tape prints (`source=ibkr_l1`, never fakes `store_series_complete`) unit-tested (4 tests) + wired into `tape_stream._on_tape_update` and `scanner_l1.flush_loop` heartbeat. Trader-seam warm fill on first tape subscriber, store-settled guarded, unit-tested (2 tests). Full backend suite: 1386 passed (excl. one pre-existing flaky transformers-import test unrelated to this change).
- **Keywords:** Loading IBKR historical, 10Sec, 1Day, Full Day, MSS, ADR 012, historical_service, 60/10 min pacing, Large Cap, open_chart, bars_store

## D-002 -- Afterhours Gap % equals Change %, not the open-vs-prior-close gap

- **Status:** open
- **Kind:** bug
- **Severity:** P1
- **Effort:** S
- **Domain:** market-feed
- **User-visible:** yes
- **Logged:** 2026-08-26
- **Why parked:** The Gainers/Losers `reprice_mover_row` path now derives `gap_percent` from the IBKR session-open tick (tick 14). The afterhours reprice path (`ibkr_bridge.apply_l1_quote` afterhours branch / `_ah_discovery`) was not migrated in that same change, and the evening session was already on the afterhours table so we could not E2E the gainer gap at the same time.
- **Blast radius:** Afterhours Gap % on every row is a lie whenever the session move is not equal to the overnight gap. An operator can treat a +50% runner as a +50% gapper.
- **Unblock:** None -- shape is known. Do it in a session that can see a live afterhours roster.
- **Next:** Thread `open_price` through the afterhours L1 reprice the same way `discovery.reprice_mover_row` does; do not reuse `change_pct` as gap. Add a regression that an AH row with open != last keeps a real gap.
- **Evidence:** 2026-08-26 live OKTG: Gap % showed `+53.29%` (same as Change %) while open vs prior close was `-2.50%`.
- **Keywords:** afterhours, gap_percent, change_pct, OKTG, _ah_discovery, apply_l1_quote, tick 14, reprice_mover_row

## D-001 -- Scanner NEWS column is dead under discovery=ibkr

- **Status:** open
- **Kind:** bug
- **Severity:** P1
- **Effort:** M
- **Domain:** news
- **User-visible:** yes
- **Logged:** 2026-08-26
- **Why parked:** Found while filling Gap % / RVOL / Float / Short Int. / Mkt Cap on IBKR movers. Every writer of `has_news` / `newest_headline_at` is still on the Alpaca-era movers/discovery runners, which early-return when `discovery=ibkr`. Fixing it is a new periodic job, not a one-line decorate, and that session was already shipping L1 + fundamentals.
- **Blast radius:** Gappers / Gainers / Losers / Afterhours NEWS column is empty every session. Catalysts elsewhere are unrelated -- this is the scanner table badge.
- **Unblock:** None on the human side. Do not write news flags into a frozen roster cache (ADR 008). Decorate at read time, same as `mover_enrich_view.decorate_rows`.
- **Next:** Periodic job over current roster symbols (the same set `mover_enrich_hooks.on_mover_roster_commit` already gathers), reuse Alpaca `_check_news`, stamp `has_news` / `newest_headline_at` at `routes/scan._strip_blocked`, `scanner_push.broadcast_roster_replace`, and `_snapshot_payload`.
- **Evidence:** 2026-08-26 live `/api/movers` Gainers rows carried neither `has_news` nor `newest_headline_at` (keys absent, not null). `scanner_runners/movers.py` returns immediately when discovery is ibkr.
- **Keywords:** has_news, newest_headline_at, NEWS column, discovery=ibkr, scanner_runners, mover_enrich_view, Alpaca news, ADR 008

<!-- OPEN_END -->

<!-- CLOSED_START -->

<!-- CLOSED_END -->
