# Nova Automation Strategy — Backbone

> This is the living master document for what the **Automate** button in Nova does.
> It is the single source of truth for automation decisions. Append, never wipe.
> Trust order: this file + `Active-Strategy.md` > Pinecone course citations > model guesses.

**Status:** DRAFT — thinking/design phase. No live orders. No code yet.
**Last updated:** 2026-07-10

---

## 0. Honest framing (read first)

There is **no guarantee** of making money in day trading. Anyone (including a course) implying a
guarantee is wrong. What we *can* engineer is a **positive-expectancy system**: a repeatable edge
where average win × win rate > average loss × loss rate, executed with strict risk caps so a bad
run can't blow up the account. "Guaranteeing money" is really **guaranteeing discipline**: the
machine follows the rules every time, never revenge-trades, never oversizes, always cuts losses.
That consistency is the closest thing to an edge that survives.

The strategy we're encoding is Ross Cameron / Warrior Trading **momentum trading** — buying
strong, high-relative-volume, low-float stocks with a news catalyst, and scalping the move.

---

## 1. The edge, in one paragraph

Small-cap stocks with a **news catalyst + low float (<20M shares) + high relative volume (≥5x) +
up ≥10% + price $2–$20** attract a crowd of momentum traders who all trade the same playbook.
That self-fulfilling crowd creates sharp, tradeable intraday moves. We enter on defined patterns
(Gap and Go, Bull Flag, ABCD), risk a few cents per share against a nearby technical level, and
take profits into strength at a 2:1 (or better) profit/loss ratio. Edge comes from **selection**
(only the best setups) + **risk asymmetry** (small stops, bigger targets) + **discipline**
(few trades, walk away after losses).

### The 5 Pillars of Stock Selection (course-verified)
Source: Basics Ch.3 p85; SS101 Ch.1 p13 & Ch.3 p64
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
- **Gap and Go** (SS101 Ch.7): premarket gapper, mark premarket high, entry on break of
  premarket high / first pullback; window 9:30–10:00 ET. Rules are explicit.
- **Bull Flag** (SS101 Ch.5 p35): 3+ green candles, 2+ red pullback candles not breaking prior
  high, pullback to 9 EMA, retrace <50% of the move; entry on break of the flag.
- **ABCD** (SS101 Ch.5 p55): big move (A→B), pullback holds above 9 EMA (C), entry on break of
  point B (D); stop ~20 cents.
- All three have **numeric, codeable triggers** (candles, EMA, prior highs). **Automatable.**

### C. Risk / trade management (the part that guarantees discipline)
Source: SS101 Ch.2, Ch.12; Basics Ch.15
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
- **Level 2 / tape reading nuance** — Ross's exact entries/exits read the L2 order book and time &
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

- **2026-07-10** — Backbone created. Chose Warrior/Ross momentum model as the strategy family.
  Decided: automate selection + setup detection + risk/journaling; do NOT automate tape-reading
  exits, catalyst judgment, or live money yet. Everything paper-first. Evidence pulled from
  Pinecone (Basics Ch.3/15, SS101 Ch.1/2/5/7/11/12 + Extra).
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
