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

### L0 -- Pick one strategy `[x]` (A1, 2026-09-22 -- see Decision log)

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

### L1 -- Get the data `[x]` (B1 bought 2026-09-22; everything the plan includes is on `F:\Nova\data\massive`: minute + day flat files 2021-09-21..2026-09-21, tickers, splits, dividends, ticker details, news archive, short data where served, one-second bars for the selected symbol-days; `research/orb/massive_reference_dump.py` manifest lists counts and anything refused)

Decision B (recommendation starred):

- **★ B1 -- Buy full-market 1-minute history including delisted tickers**, 5+ years
  (Polygon/Massive or FirstRateData). Small-cap losers get delisted; a survivors-only dataset
  lies.
- **B2 -- IBKR-only via Sim history.** Spot-checks at tape level only; unusable for a universe
  test (pacing, no delistings).
- **B3 -- Databento tick data.** Overkill until fills, not signals, are the question.

Done when: one local Parquet / DuckDB store with a "was listed on that date" flag per symbol.

### L2 -- Backtest `[x]` for A1 (2026-09-22, see §2b); `[ ]` for A2

Install vectorbt in a scratch environment, adapt `.cursor/skills/backtest/` to read the local
store, code the ORB rules exactly as published. Charge IBKR commissions plus 1-3 c/share slippage
on small caps; no signal may read anything after its own minute.

Done when: the ORB reproduces the paper's *shape* on 2016-2023 and the run reports trade count,
expectancy in R, profit factor, max drawdown.

### L3 -- Try to break it `[x]` for A1 (broke on the 2x-cost test, see §2b); `[ ]` for A2

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

## 2b. Gate 1 result -- ORB long-only, 2026-09-22 (harness: `research/orb/`)

Data: every US stock, 1-minute bars 2021-09-21 .. 2026-09-21 (1,255 days), delisted names
included, funds / warrants / units and split-window days excluded via the reference tables.
Account modelled: $25,000 cash, no margin, IBKR fixed commission ($0.005/share, min $1) plus
$0.01/share slippage on every fill, 1% risk per position, notional capped at 25% of equity.

| Run | Trades | Win | PF | Exp | CAGR | Max DD | Sharpe |
|---|---|---|---|---|---|---|---|
| **Published rule** (top 20, stop 0.10 ATR) | 3,919 | 12.1% | 1.20 | +0.23R / $14 | 26.4% | -20.1% | 1.05 |
| Zero slippage, same commission | 3,917 | 13.1% | 1.36 | +0.40R | 47.6% | -12.3% | 1.66 |
| Paper's costs ($0.0035, no slippage) | 3,918 | 13.1% | 1.40 | +0.43R | 51.6% | -11.6% | 1.77 |
| Slippage $0.02 | 3,917 | 11.1% | 1.06 | +0.05R | 7.6% | -30.6% | 0.41 |
| Slippage $0.03 | 3,922 | 10.5% | 0.95 | -0.12R | -6.8% | -50.7% | -0.17 |
| **2x costs** ($0.01/share, $0.02 slip) | 3,918 | 11.1% | 1.00 | -0.02R | -0.2% | -36.6% | 0.11 |
| Stop 0.05 ATR (best neighbour) | 3,915 | 7.8% | 1.41 | +0.53R | 28.2% | -10.9% | 1.30 |
| Stop 0.20 ATR | 3,945 | 20.6% | 1.07 | +0.05R | 13.8% | -34.8% | 0.60 |
| Stop 0.50 ATR | 4,247 | 37.2% | 1.02 | +0.01R | 5.9% | -47.9% | 0.34 |

Top 10 / 20 / 30 by relative volume give the same numbers: with a cash account the first
four or five orders use all the buying power, so rank 11+ rarely trades. Entry cutoff 10:30
vs 15:30 and 0.5% vs 1% risk change nothing material. Every calendar year is positive
(2023: +$334 and 2026 YTD: +$189 are effectively flat).

**Structure of the profit (base run):** the 10 best trades out of 3,919 are 123% of the
total P&L -- without them the five years lose $12,324; the best 25 are 199%. Winners hold
all day (median 383 min), losers are gone in 2 minutes. 96% of days sit below the previous
equity peak; the worst drawdown ran 14 months (2025-05 to 2026-07). Months positive: 29 of
60. Rank buckets: ranks 1-5 carry +0.25R, 6-10 +0.20R, 11-20 negative -- the relative-volume
ordering is real information, not noise.

**Kill criteria, pre-registered in §2, L3:**

| Criterion | Result |
|---|---|
| Edge lives in one year | Pass -- five of six years positive, two flat |
| Fewer than 300 trades | Pass -- 3,919 |
| Neighbourhood mostly positive | Pass -- all 12 stop x top cells positive, decaying past 0.2 ATR |
| **Dies at 2x costs** | **Fail** -- profit factor 1.00, CAGR -0.2% |

**Verdict: the published rule does not pass gate 1 for this account.** The signal is real
(rank structure, +0.4R at zero slippage, the paper's shape reproduced), but the whole edge
sits inside one to two cents per share of slippage, and it is carried by about ten trades
in five years. At $25k with no leverage that is a bet on catching the next ten runners
without a halt, a bad fill or a missed morning. It is not something to put money behind.

**Comparison row:** the free SPY swing baseline (five published mean-reversion rules,
1993-2026, 0.03% per side) reproduces its source within a point: combined 10.3% CAGR, 72%
win rate, 43% time in market, max DD -23.7%, 1,045 trades; buy-and-hold 8.9% with -56.5%.

**What follows (agent decisions, standing veto):**

1. **A2 Gap and Go on the same store** as the second candidate, once the news archive and
   the per-ticker details (float, market cap) finish downloading -- its catalyst and float
   pillars need exactly those. Same harness, same costs, same kill criteria.
2. The **0.05 ATR ORB variant** is recorded as the best neighbour but is *not* promoted: it is
   an in-sample pick, it keeps 88% of its profit in the ten best trades, and it fails the
   same cost test at 2x.
3. **One-second bars** for the selected symbol-days (09:30-11:00 ET) were pulled while the
   plan was active, so the entry-bar stop question can be settled if ORB is ever revisited.

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
| 2026-09-22 | **Decision B = B1.** Operator bought Massive (formerly Polygon) Stocks Starter for one month; flat files `us_stocks_sip/minute_aggs_v1` + `day_aggs_v1` from 2021-10-01 download to `F:\Nova\data\massive` (~24 GB, unadjusted -- splits pulled via REST before cancelling). S3 pair lives in the desk `.env` as `MASSIVE_S3_*`. | Operator |
| 2026-09-22 | **Decision A = A1** (5-minute ORB on stocks in play, long-only first), decided by the agent at the operator's request ("I just want to be profitable, I don't know") -- the only candidate with a replicated published backtest and a universe Nova's scanner already produces. A3 (SPY swing on free daily bars) runs alongside as the baseline; A2 (Gap and Go) follows on the same harness. Operator may veto. | Claude Fable 5.1 for the operator |
| 2026-09-22 | **Gate 1 verdict for A1: not passed** (fails the 2x-cost kill test; profit carried by ~10 trades). Not promoted to paper. **Next candidate: A2 Gap and Go** on the same store once news + ticker details are in. Operator's definition of done unchanged: paper evidence, then their live test. | Claude Fable 5.1 for the operator |
