# Bot Trading Plan (Phase L -- strategy proof)

> **Status:** Product NEXT since 2026-09-22 (operator direction). Supersedes Phase K as the
> active roadmap phase; K is parked (see [[Nova-Roadmap-Status]]).
> Trust order: [[Nova-Roadmap-Status]] > this note > [[Active-Strategy]] > [[Automation-Strategy-Backbone]] > model guesses.

## 0. The honest framing

Nobody who does this well "trains" a bot the way a model is trained. The bots that work are
dumb: one mechanical strategy with a stated reason it should work, tested on years of data with
honest costs, attacked until it breaks or survives, run on paper until live numbers match the
test, then live at tiny size. Machine-learning, reinforcement-learning and LLM "brains" fail for
retail because markets are noisy, non-stationary and adversarial, and costs eat the edges they
find (FINSABER, arXiv 2505.07078: LLM timing strategies underperform passive benchmarks over
two decades and 100+ symbols). Nova's `llm-decide` pack is a news-triage filter, never the brain.

## 1. Where Nova stands (2026-09-22)

| Stage | Needs | Nova today |
|---|---|---|
| Strategy rules | Numeric entry / stop / target / size / window | Gap and Go chosen in [[Active-Strategy]]; `backend/strategy/` holds signal-only detectors. Exits like "weakness" are not numeric. |
| Data | Years of 1-minute bars **including delisted names** | Archive `bars_1m` holds a few hundred bars. Sim history downloads one symbol, one day, one request per 11 s; IBKR has no delisted symbols. **No dataset.** |
| Backtest | Engine with costs and no lookahead | `backend/backtest/` walks archive days honestly but hard-codes every candidate (`BACKTEST_CANDIDATE_REL_VOLUME=5`, `HAS_NEWS=True`, `FLOAT=5M`), so it tests the pattern, never the selection. vectorbt skills are vendored, the library is not installed, and the templates target Indian OpenAlgo data. |
| Robustness | Walk-forward, permutation, cost sensitivity | None. |
| Paper | Live feed, estimated fills, journal | The Paper venue (ADR 020) plus `/api/practice/history`. Sim replays recorded sessions (ADR 019). |
| Bot | Executes rules under caps | Nova OS executor ladder (`signal` -> `confirm` -> `auto_paper`) and the bot localhost API (ADR 016: L0/L1/L2, packs, -$50 / -$200 breakers). |
| Live | Gated | IBKR flags, header arming (ADR 018), `auto_live` NO-GO. |

The first three rows are the gap. Everything after them is built.

## 2. Stages and done-criteria

### L0 -- Pick one strategy `[ ]`

Decision A (recommendation starred):

- **★ A1 -- 5-minute Opening Range Breakout on "stocks in play"** (Zarattini, Barbon & Aziz
  2024, SSRN 4729284; QQQ variant SSRN 4416622). The only intraday momentum strategy with a
  peer-reviewed backtest that outsiders have replicated; its universe is what Nova's gapper and
  RVOL scanners already produce; every rule is a number.
- **A2 -- Gap and Go** (current [[Active-Strategy]]). Test second, on the same harness: the
  pre-market-high break and the discretionary exits need decisions before they can be coded.
- **A3 -- Large-cap swing mean reversion on daily bars.** Fully numeric, cheap data, different
  product than the day-trading desk. Boring baseline to compare against.

Published ORB rules (the bar for "fully numeric"):

| Rule | Value |
|---|---|
| Universe | Open > $5, 14-day average volume >= 1M shares, 14-day ATR > $0.50 |
| Selection | Top 20 by opening relative volume = first-5-minute volume / its 14-day average |
| Entry | Buy stop at the 5-min high if the first candle is green; sell stop at the low if red; nothing on a doji |
| Stop | 10% of the 14-day ATR from entry |
| Target | None; exit at the close |
| Risk | 1% of equity per position, 4x leverage cap |
| Costs assumed | $0.0035 / share |
| Reported 2016-2023 | 41.6% annualized, Sharpe 2.81, max DD 12%, hit rate 48.4% |

Replicator caveats: no clean out-of-sample period, simplified fills, and the QQQ variant breaks
even at ~2.2 c/share slippage. Expect lower numbers. **Test the long-only variant first** --
shorting is gated behind the parked Phase K.

Done when: Decision A recorded in this note's Decision log with the operator's choice.

### L1 -- Get the data `[ ]`

Decision B (recommendation starred):

- **★ B1 -- Buy full-market 1-minute history including delisted tickers**, 5+ years
  (Polygon/Massive or FirstRateData). Small-cap losers get delisted; a survivors-only dataset
  lies.
- **B2 -- IBKR-only via Sim history.** Spot-checks at tape level only; unusable for a universe
  test (pacing, no delistings).
- **B3 -- Databento tick data.** Overkill until fills, not signals, are the question.

Done when: one local Parquet / DuckDB store with a "was listed on that date" flag per symbol.

### L2 -- Backtest `[ ]`

Install vectorbt in a scratch environment, adapt `.cursor/skills/backtest/` to read the local
store, code the ORB rules exactly as published. Charge IBKR commissions plus 1-3 c/share slippage
on small caps; no signal may read anything after its own minute.

Done when: the ORB reproduces the paper's *shape* on 2016-2023 and the run reports trade count,
expectancy in R, profit factor, max drawdown.

### L3 -- Try to break it `[ ]`

Walk-forward by year. Parameter neighbourhood: stop 5 / 10 / 15% ATR, top 10 / 20 / 30 by RVOL,
5 / 15 / 30-minute ranges -- the neighbourhood must stay positive. 1,000-shuffle permutation
test. Double the costs. Split by regime (2021 vs 2022-23).

Kill criteria: edge lives in one year, dies at 2x costs, < 300 trades, or permutation p > 0.05.

### L4 -- Paper on Nova `[ ]`

Encode the surviving rules as a bot pack or Nova OS setup. Run L1 Eyes (bot proposes, human
places), then L2 Strategy on the Paper venue. Journal through `/api/practice/history`.

Done when: 100 trades with expectancy within ~30% of the backtest and slippage measured.

### L5 -- Tiny live `[ ]`

Under the existing gates, after #444 (one-share test gate on practice venues) is answered.
Double size only after each 50-trade block stays positive; pause when live drawdown exceeds the
backtest's worst. `auto_live` stays NO-GO -- live orders stay operator-armed.

## 3. Reference numbers (from the 2026-09-22 research pass)

- Good backtest: > 300 trades, profit factor 1.3-2.0 after costs, expectancy > 0.2R, max DD
  < 20%, no single year carrying the result. Sharpe 5 or an 80% win rate on small caps is a
  bug, usually lookahead.
- Small-cap gaps fade: one dataset puts the average pre-market high at +71.5% with the open
  retracing 84.5% of it -- "gap up, buy the open" loses by itself; catalyst + float filters
  are the strategy.
- Sizing: 0.5-1% of equity at risk per trade keeps risk of ruin under 5% over 100+ trades for
  a real edge; cap at a quarter of Kelly. Nova's breakers sit under this.
- Paper duration: 30-60 days or 50-100 trades across conditions.
- Signal vendors: an independent 45-day test of Holly AI found 62-64% accuracy and no audited
  track record; Nova already has the scanner half.

Sources: danfin.net/opening-range-breakout-research · concretumgroup.com (ORB, data-provider
dispersion) · github.com/giovannibrusco/zarattini-2023-orb-qqq · arxiv.org/abs/2505.07078 ·
quantifiedstrategies.substack.com (five SPY swing rules) · susanpotter.net backtest-bias
taxonomy · Bailey & Lopez de Prado, Deflated Sharpe Ratio · smallcaplab.com/research ·
blog.traderspost.io paper-to-live guide.

## 4. Decision log (append-only)

| Date | Decision | By |
|---|---|---|
| 2026-09-22 | Plan authored; Phase K parked; this note is product NEXT. Decisions A and B open. | Operator + Claude Fable 5.1 |
