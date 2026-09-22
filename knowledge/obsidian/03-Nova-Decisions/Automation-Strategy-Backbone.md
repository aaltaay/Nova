# Nova Automation Strategy — Backbone

> This is the living master document for what the **Automate** button in Nova does.
> It is the single source of truth for automation decisions. Append, never wipe.
> Trust order: this file + `Active-Strategy.md` > Pinecone reference citations > model guesses.

**Status:** DRAFT — thinking/design phase. No live orders. No code yet.
**Last updated:** 2026-07-10

---

## 0. Honest framing (read first)

There is **no guarantee** of making money in day trading. Anyone implying a
guarantee is wrong. What we *can* engineer is a **positive-expectancy system**: a repeatable edge
where average win × win rate > average loss × loss rate, executed with strict risk caps so a bad
run can't blow up the account. "Guaranteeing money" is really **guaranteeing discipline**: the
machine follows the rules every time, never revenge-trades, never oversizes, always cuts losses.
That consistency is the closest thing to an edge that survives.



---

## 1. The edge, in one paragraph

Small-cap stocks with a **news catalyst + low float (<20M shares) + high relative volume (≥5x) +
up ≥10% + price $2–$20** attract a crowd of momentum traders who all trade the same playbook.
That self-fulfilling crowd creates sharp, tradeable intraday moves. We enter on defined patterns
(Gap and Go, Bull Flag, ABCD), risk a few cents per share against a nearby technical level, and
take profits into strength at a 2:1 (or better) profit/loss ratio. Edge comes from **selection**
(only the best setups) + **risk asymmetry** (small stops, bigger targets) + **discipline**
(few trades, walk away after losses).

### The 5 Pillars of Stock Selection (operator's playbook)
1. **Price** — best $2–$20 (exceptions allowed).
2. **% Change Today** — up ≥10% vs prior close (or ≥10% off LOD on continuation).
3. **Relative Volume** — at least **5x** average.
4. **Catalyst** — ideally breaking news; a clean daily-chart technical breakout can substitute.
5. **Float** — best under **20M** shares (lower float → bigger % moves).

---

## 2. What we CAN automate (high confidence)

These are mechanical and map directly onto Nova's existing scanner data.

### A. The Scanner / Watchlist builder (Nova already does most of this)
- Filter the universe by the 5 Pillars every morning + intraday.
- Rank candidates by a composite score (gap %, RVOL, float, catalyst freshness).
- This is Nova's core strength today (gappers, movers, HOD momo, news catalyst panel).
- **Automatable: 100%.** This is signal generation, not order execution.

### B. Setup detection (pattern recognition on bars)
  premarket high / first pullback; window 9:30–10:00 ET. Rules are explicit.
  high, pullback to 9 EMA, retrace <50% of the move; entry on break of the flag.
  point B (D); stop ~20 cents.
- All three have **numeric, codeable triggers** (candles, EMA, prior highs). **Automatable.**

### C. Risk / trade management (the part that guarantees discipline)
- **Position sizing:** start 100-share blocks; ¼ size until a profit cushion (~¼ of daily goal),
  then scale up; cut size after a loss >10% of the day.
- **Profit/Loss ratio:** minimum 1:1, target **2:1** (wins bigger than losses).
- **Stops:** tight, cents-based (e.g. 5–10¢ preferred, 20¢ max on scalps).
- **Daily max loss = daily goal** (walk-away trigger).
- **Guardrails:** walk away after first loss / after giving back X% of gains / after 3 losses in a row.
- These are pure arithmetic + state machine → **fully automatable and the highest-value part.**

### D. Journaling / feedback loop
- Log every signal + (paper) fill + outcome; compute win rate, avg win/loss, P/L ratio.
- Feed weekly summaries back into this vault. **Automatable.**

---

## 3. What we should NOT (yet) automate

- **Catalyst quality judgment** — "is this news *actually* meaningful?" LLM can *assist* triage,
  but blindly trusting headline scraping = false signals. Keep a human/LLM check before size.
- **Level 2 / tape reading nuance** — the discretionary entries/exits read the L2 order book and time &
  sales ("big seller on the ask", "buying drying up"). Nova's Alpaca feed is IEX (thin); real L2
  needs the IBKR module. Until L2 is wired + tested, don't automate tape-based exits.
- **Discretionary "feel" for market conditions** (hot vs cold day). Encode later as a regime flag;
  don't let the bot trade full size in chop.
- **Live money.** Everything starts and stays in **paper** until metrics prove the edge.
  (IBKR live requires `IBKR_ENABLED=true` AND `IBKR_LIVE_TRADING_CONFIRMED=true`.)
- **Anything during the first live sessions without a human watching.** Signal-only first.

---

## 4. Why this fits Nova specifically

- Nova already scans gappers, movers, HOD momentum, and has a news-catalyst panel → the 5 Pillars
  and setup detection sit on top of existing data with minimal new plumbing.
- There is already an **HOD Momo** module — Gap and Go / breakout detection overlaps it.
- The optional **IBKR module** provides paper execution + (later) real Level 2 for tape-based exits.
- So Nova's natural first automation = **"signal the setup, size the risk, (paper) execute, journal."**

---

## 5. Phased plan (no money at risk early)

1. **Phase 1 — Signal only.** Bot flags valid setups (5 Pillars + pattern) and the exact risk
   (entry, stop, target, share size). No orders. Human reviews. Log everything.
2. **Phase 2 — Paper execution (IBKR paper).** Auto-place bracket-style paper orders on flagged
   setups with hard risk caps. Journal fills. Prove positive expectancy over N trades.
3. **Phase 3 — Tighten.** Remove setups/conditions that lose. Add market-regime gating.
4. **Phase 4 — Consider live**, tiny size, only if paper metrics clear a pre-set bar
   (e.g. P/L ratio ≥ 2:1 and win rate ≥ target over ≥100 trades). Requires explicit live flags.

**Go/no-go metric bar (set before going live):**
- Profit/loss ratio ≥ **2:1**
- Adherence: 100% of trades within rules (no oversize, no missed stop)
- Max daily loss never breached by the bot

---

## 6. Open decisions (fill as we go)

- [ ] Which setup first? (Recommend **Gap and Go**, cleanest rules + fits gapper scanner.)
- [ ] Exact composite ranking score formula.
- [ ] Daily goal / daily max-loss dollar values for the paper account.
- [ ] Where does the "Automate" button live in the UI, and what does one click do?
- [ ] Catalyst-quality check: rules-based, LLM-assisted, or human-gate?

---

## 7. Decision log (append-only)

  Decided: automate selection + setup detection + risk/journaling; do NOT automate tape-reading
  exits, catalyst judgment, or live money yet. Everything paper-first. Evidence pulled from
- **2026-07-10** — Implemented Phase 1 ("signal only") for the Five Pillars and Gap and Go:
  `backend/strategy/five_pillars.py` scores any candidate dict against all 5 pillars and returns
  a checkmark only when all 5 pass; `backend/strategy/gap_and_go.py` adds the time-window +
  premarket-high-break check and computes entry/stop/target math, with `would_execute` hard-coded
  `False`. Exposed read-only via `GET /api/strategy/five-pillars[/{symbol}]` and
  `GET /api/strategy/gap-and-go/{symbol}` (`backend/routes/strategy.py`) — no order-placing code
  path exists anywhere in this module. 22 unit tests cover both modules against mock data (see
  `backend/tests/test_five_pillars.py`, `test_gap_and_go.py`); full spec at
  `02-Strategies/Five-Pillars-and-Gap-and-Go-Spec.md`.
  **Transparency principle adopted:** any UI control tied to automation (an "Automate" button,
  a signal panel, etc.) must state in plain language, next to the control, exactly what it does
  and does not do (e.g. "Signal only — no orders are placed"). No control may trigger behavior
  the user wasn't told about. This applies to every phase, including Phase 2 paper execution.
- **2026-07-11** — Adopted the full 6-phase automation build plan (Watchlist -> Setups -> Risk ->
  Journal -> Paper Execution -> Level 2 learning). Order chosen so the journal exists before any
  order is ever placed. Implemented **Phase A (Watchlist dashboard)**: `backend/strategy/watchlist.py`
  adds a weighted composite score (change %, RVOL, float tightness, catalyst freshness — constants
  in `backend/constants.py` `WATCHLIST_*`) on top of Five Pillars scoring; all-pillars-pass symbols
  always rank above partial passes. Exposed via `GET /api/strategy/watchlist` (merges gapper +
  gainer caches, deduped by symbol). New frontend module `frontend/src/strategy/` (`WatchlistTab.tsx`,
  `useWatchlist.ts`, `types.ts`) adds a **Watchlist** tab to `TabNav` showing per-pillar pass/fail
  chips, sub-scores, and composite rank; polls continuously so the tab badge count stays live.
  12 new unit tests (`backend/tests/test_watchlist.py`). Verified live against the running scanner
  (30 ranked candidates returned, correct pillar chips) and in-browser via headless screenshot.
- **2026-07-11** — Implemented **Phase B (Setup trigger engine)**: `backend/strategy/indicators.py`
  adds shared pure helpers (`ema()`, `is_green()`/`is_red()`) reused by two new pattern modules —
  `bull_flag.py` (flagpole of 3+ green candles -> shallow pullback holding the 9 EMA, retrace <50%,
  entry on break back above the flagpole high) and `abcd.py` (impulsive A-B move >=5%, pullback C
  holding the 9 EMA, entry D on break back above point B, fixed 20c stop per the playbook).
  Both mirror `gap_and_go.py`'s contract exactly: pure functions, `would_execute` hard-coded `False`,
  full `notes` explaining why a signal isn't eligible yet. `setups.py` aggregates all three into one
  `evaluate_setups()` call. Exposed on-demand via `GET /api/strategy/setups/{symbol}` and live via a
  new `strategy/setups_stream.py` background loop (`SETUPS_SCAN_INTERVAL_SEC` = 15s, scans the top
  `SETUPS_SCAN_TOP_N` watchlist symbols, per-symbol+setup cooldown `SETUPS_ALERT_COOLDOWN_SEC` to
  avoid repeat spam) broadcasting over a new `/ws/strategy` WebSocket — same client-set pattern as
  `hod_momo.py`'s `/ws/hod-momo`. Frontend: `useSignalsStream.ts` + `SignalsPanel.tsx` add a
  **Signals** sub-tab inside the Watchlist tab showing live triggers with entry/stop/target and the
  latest note. 34 new unit tests (`test_indicators.py`, `test_bull_flag.py`, `test_abcd.py`,
  `test_setups.py`) — 75/75 full backend suite green. Verified live: `/api/strategy/setups/{symbol}`
  and `/ws/strategy` both tested against the running scanner with real 1-min bars (pattern math
  correct, no order-placing code path anywhere in the chain); Signals sub-tab confirmed connected
  in-browser via headless screenshot.
- **2026-07-11** — Implemented **Phase C (Risk / discipline engine)**: `backend/strategy/risk.py`
  is a pure `RiskState` state machine (no orders, ever) tracking today's realized P&L, win/loss
  streaks, and a "peak" high-water mark. Position sizing follows the playbook exactly — 100-share
  blocks, quarter size (`RISK_QUARTER_SIZE_MULTIPLIER`) until a profit cushion of ¼ the daily goal
  (`RISK_PROFIT_CUSHION_FRACTION`) is reached, then a `RISK_SIZE_CUT_MULTIPLIER` cut after losing
  more than 10% of the daily goal — sizing reacts to *current* P&L, not the day's peak, so giving
  back a cushion drops you back down. Three walk-away guardrails halt the day (sticky until
  `reset_day()`): daily max loss = daily goal (`RISK_DAILY_GOAL_DOLLARS`, currently a placeholder
  constant pending a real Settings field), 3 losses in a row (`RISK_MAX_CONSECUTIVE_LOSSES`), and
  giving back 50% of the day's peak profit (`RISK_MAX_GIVEBACK_FRACTION_OF_PEAK`).
  `validate_trade_plan()` separately checks the 20c stop ceiling and the 1:1 profit/loss floor.
  Exposed read-only via `GET /api/strategy/risk` and `POST /api/strategy/risk/validate-trade`; a
  `session_reset_loop()` (mirrors `hod_momo.py`'s pattern) resets state at 4 AM ET. 15 new unit
  tests (`test_risk.py`) — 90/90 full backend suite green. No frontend UI yet — the go/no-go bar
  ships with Phase E (Journal), which will read this same `/api/strategy/risk` endpoint.
- **2026-07-11** — Implemented **Phase E (Journal + go/no-go bar)**: new `backend/journal/` package
  (`db.py`/`store.py`/`metrics.py`) persists every setup signal to a SQLite `signals` table the
  moment `setups_stream.py` detects it — the journal exists and is already logging before any
  order-placing code (Phase D) is written. A `trades` table + `record_trade()` are ready for Phase D
  to populate; until then, `metrics.compute_metrics()` honestly reports `null`/pending rather than a
  fabricated rate from zero trades. The go/no-go bar checks the plan's three live-money criteria
  (`JOURNAL_MIN_TRADES_FOR_GO_LIVE` = 100 closed trades, `RISK_TARGET_PROFIT_LOSS_RATIO` = 2:1,
  100% adherence) and folds "max daily loss never breached" into the adherence flag itself — a trade
  marked non-adherent covers any risk-rule violation, including trading through a halt. Exposed via
  `GET /api/journal/{signals,trades,metrics}`; new **Journal** sub-tab (next to Watchlist/Signals)
  renders the bar, a metrics grid, and recent signals. 8 new unit tests (`test_journal.py`) — 98/98
  full backend suite green. Verified live against the running scanner (metrics/signals endpoints
  correct) and in-browser via headless screenshot (NO-GO bar + empty-state metrics render correctly
  with zero trades). Next: **Phase D (paper execution)**.
- **2026-07-11** — **Journal E2E hardening**: since Phase D doesn't exist yet, the `trades` table has
  no real feeder, so there was no way to actually exercise the metrics/go-no-go math or see the UI
  populated. Added an `is_mock` column on `trades` (auto-migrated in for existing DBs via a
  `PRAGMA table_info` check in `init_db()`), a fixed 12-trade synthetic dataset
  (`backend/journal/mock_data.py`, seeded/cleared only from the terminal —
  `py -3 -m journal.mock_data seed|clear`, deliberately never a clickable API action), and an
  `include_mock` param on `/api/journal/{trades,metrics}` that defaults `False` everywhere so real
  go/no-go results can never be silently inflated by test data. The Journal panel got a "Show demo
  data" checkbox (off by default) that shows a persistent "DEMO DATA ACTIVE" banner and a `DEMO` chip
  on every synthetic row whenever checked — full transparency, no hidden state. Also wired in the real
  `/api/strategy/risk` status as a "Today's risk state" card (the piece promised in the Phase C entry
  above but not actually delivered until now), and added `title=` hover tooltips to every interactive
  element and metric across Watchlist/Signals/Journal so hovering explains exactly what each number
  means and where it comes from. 104/104 backend tests green (6 new). Verified live: seeded the mock
  set against the running dev server, confirmed default responses exclude it while `?include_mock=true`
  shows a deliberately mixed pass/fail/pending go/no-go result (58.3% win rate, 2.22:1 P/L ratio, 91.7%
  adherence), screenshotted the populated UI in a headless browser, unchecked the toggle and confirmed
  it reverted to the honest empty state, then cleared the mock rows so the dev DB is clean again. Along
  the way, found and fixed a `uvicorn --reload` orphan-worker bug that was serving stale code (logged in
  `PROBLEM_LOG.md`) — killing only the reloader PID left its child worker running on the same port.
  Next: **Phase D (paper execution)**.
- **2026-07-11** — Implemented **Phase D (Paper execution via IBKR)**: `backend/ibkr/orders.py`
  gained `place_bracket_order()` using `ib_async`'s native `IB.bracketOrder()` helper (LMT entry +
  linked LMT target + linked STP stop; TWS handles the OCA cancel-the-other-leg behavior natively —
  nothing here reimplements that), gated by the same `_safety_check()` (`IBKR_ENABLED`, connected,
  paper-vs-`IBKR_LIVE_TRADING_CONFIRMED`) as every other order call. New `backend/strategy/executor.py`
  is the only caller: it starts **disarmed on every restart** and only places an order when ALL of
  (1) armed, (2) `risk.can_trade()`, (3) `risk.validate_trade_plan()`, (4) no existing open position
  for that symbol pass — hooked into `setups_stream._scan_once()` right after a signal is journaled,
  wrapped in its own try/except so an executor failure can never break the signal broadcast. A
  background `fill_poll_loop()` (mirrors `setups_stream.scan_loop()`) polls IBKR's open orders every
  `EXECUTOR_FILL_POLL_INTERVAL_SEC`; once none of a bracket's three order IDs remain open, it resolves
  the fill from `ib.fills()`, records the trade to the journal (a trade is only ever written once, at
  close — matches the original design note in `journal/store.py`, so no schema change was needed), and
  calls `risk.record_trade_result()`. New `backend/routes/executor.py` exposes
  `GET /api/strategy/executor/status` and `POST .../arm|disarm|kill-switch|reset-kill-switch` — the
  **only** endpoints that can turn automated order placement on, each returning the plain-language
  disclosure inline. Frontend: new **Automation** sub-tab (`ExecutorPanel.tsx` + `useExecutor.ts`)
  shows the armed/disarmed/kill-switch state, IBKR connection status, and open automated positions;
  arming requires a native `confirm()` dialog that restates the disclosure verbatim before the click
  takes effect — per the transparency principle, nothing here can be armed by an accidental click.
  **Known, deliberate limitation:** open positions are tracked in executor memory only (not the DB),
  so a backend restart mid-bracket loses the in-app record (IB itself is unaffected); acceptable for a
  paper-trading learning tool, called out explicitly in the module docstring. Kill switch cancels this
  module's own open bracket orders but does **not** flatten an already-filled position — that stays a
  deliberate human decision. All current setups (Gap and Go, Bull Flag, ABCD) are long-only, so the
  entry side is a fixed constant (`EXECUTOR_ENTRY_SIDE_IBKR`/`_JOURNAL`) for now. 17 new unit tests
  (`test_executor.py`, IBKR/risk mocked, no live Gateway needed) — 121/121 full backend suite green.
  Verified: `main.py` boots with the new router + background task wired into the lifespan; frontend
  builds clean (`tsc -b && vite build`) with no new lint errors. Not yet verified against a live IB
  Gateway paper session (none was running this session) — that remains the real-world proof pending a
  manual test with Gateway up. Next: **Phase F (Level 2 learning)**.
- **2026-07-11** — Implemented **Phase F (Level 2 learning — record first, automate later)**: new
  `backend/l2/` package. `recorder.py` hooks into `setups_stream._scan_once()` the same
  try/except-wrapped way the executor does — on every signal it subscribes IBKR depth for that symbol
  (reusing `ibkr/depth.py`'s existing subscription refcounting so it never exceeds IBKR's symbol cap
  or steps on an already-open `DepthLadder` subscription) and snapshots `current_book()` every
  `L2_SNAPSHOT_INTERVAL_SEC` for `L2_RECORD_WINDOW_SEC` around the signal, writing rows to a new
  `l2.db` (`l2_snapshots` table, own SQLite file per the journal's one-db-per-domain pattern) via
  `l2/store.py`. `l2/features.py` is pure math, no I/O: `bid_ask_imbalance`, `is_ask_stacked`,
  `is_bid_heavy` (single-snapshot), and `is_buying_pressure_drying_up` (trailing-window comparison,
  needs >= 2 snapshots) — these are the same qualitative tape reads, turned into
  numbers. `l2/labeling.py` joins each recording's signal symbol/timestamp against
  `journal.store.get_trades()` (closest matching trade within `L2_LABEL_MATCH_TOLERANCE_SEC`, mock
  trades excluded by default) to tag each recording `win`/`loss`/`unlabeled` — this labeled set is the
  future training data, not consumed by anything yet. New `GET /api/l2/recordings` (`routes/l2.py`)
  returns labeled recordings for future analysis tooling; read-only, no control surface needed since
  recording is fully automatic. Frontend: per the plan's "heuristic badges, not automation yet" scope,
  added single-snapshot heuristic badges (`ibkr/l2Heuristics.ts`, mirrors the backend's single-snapshot
  math exactly so what a trader sees on the live `DepthLadder` matches what gets recorded/labeled) —
  "Seller stacked on ask" / "Bid heavy" / "Wide spread" badges above the ladder, thresholds duplicated
  intentionally in `frontend/src/constants.ts` (`L2_ASK_STACKED_RATIO`/`L2_BID_HEAVY_RATIO`/
  `L2_SPREAD_WIDE_DOLLARS`, commented as mirroring backend/constants.py) since the frontend has no
  shared-constants build step. Deliberately did **not** wire the multi-snapshot "drying up" feature or
  any L2 read into the executor or risk engine — per section 3 of this doc, tape-based automation
  waits until enough labeled recordings exist to trust a rule or model; today's badges are a live
  display aid only. 23 new unit tests (`test_l2.py`: features, store, recorder subscribe/unsubscribe
  refcounting, labeling match/no-match/tolerance/mock-exclusion) — 144/144 full backend suite green.
  Verified: `main.py` boots with `l2.db` initialized and the new router registered (58 routes total);
  frontend builds clean (`tsc -b && vite build`) and lints clean. Not yet verified against a live IB
  Gateway paper session with real depth data (none was running this session). **All six plan phases
  (A–F) are now implemented.**

<!-- AGENT_DREAM_FOOTER_START -->
**Last agent dream pass:** 2026-07-18 · hygiene: [[_Agent-Dream-Hygiene]] · run `py -3 tools/agent_dream.py`
<!-- AGENT_DREAM_FOOTER_END -->
