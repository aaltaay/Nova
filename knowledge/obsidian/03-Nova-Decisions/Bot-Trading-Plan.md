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

### L2 -- Backtest `[x]` for A1 (§2b), A2 (§2c), A4 (§2d) and S1 (§2e); A5 parked

Install vectorbt in a scratch environment, adapt `.cursor/skills/backtest/` to read the local
store, code the ORB rules exactly as published. Charge IBKR commissions plus 1-3 c/share slippage
on small caps; no signal may read anything after its own minute.

Done when: the ORB reproduces the paper's *shape* on 2016-2023 and the run reports trade count,
expectancy in R, profit factor, max drawdown.

### L3 -- Try to break it `[x]` for A1 (broke on the 2x-cost test, §2b), A2 (broke on three of four, §2c), A4 (broke on three of four, §2d) and S1 (broke on three of four, §2e); A5 parked

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

## 2c. Gate 1 result -- Gap and Go long-only, 2026-09-22 (harness: `research/orb/`)

Rules were fixed in `select_gng.py` / `backtest_gng.py` before the run (Five Pillars at
09:30: $2-20, gap >= 10% vs prior close, pre-market volume >= 5x its 14-day average and
>= 100k shares, a news article for the ticker since the prior close, float <= 20M; buy stop
at the pre-market high until 10:00; stop min($0.20, 4%); half off at 2R with the stop to
breakeven; rest at 4R or an 11:30 time stop). Same account, costs and fills as §2b.

**Float caveat found on the way:** the API returns share counts only for tickers that still
exist (13,805 of 36,640), so the float pillar silently drops most delisted names -- the
ones that lost. The five-pillar run is therefore a flattering upper bound; the run without
the float pillar is the honest one.

| Run | Cands | Trades | Win | PF | Exp | CAGR | Max DD | Sharpe |
|---|---|---|---|---|---|---|---|---|
| Five pillars (survivor-biased) | 549 | 154 | 40.9% | 1.15 | +0.12R / $24 | 2.9% | -17.1% | 0.61 |
| **Without float pillar (honest)** | 2,682 | 778 | 36.9% | **1.00** | +0.05R / $0.64 | **0.4%** | **-34.4%** | 0.12 |
| Stop $0.10 | 549 | 154 | 39.6% | 0.93 | +0.05R | -1.0% | -15.7% | -0.23 |
| Stop $0.30 | 549 | 154 | 41.6% | 1.15 | +0.11R | 3.0% | -19.7% | 0.62 |
| Half off at 1.5R | 549 | 154 | 45.5% | 1.03 | +0.04R | 0.5% | -16.0% | 0.18 |
| Half off at 3R | 549 | 154 | 28.6% | 0.87 | -0.05R | -2.8% | -29.2% | -0.41 |
| No second target, hold to close | 549 | 154 | 40.9% | 0.85 | -0.08R | -3.1% | -31.3% | -0.55 |
| Entries until 10:30 | 549 | 173 | 41.0% | 1.13 | +0.12R | 2.9% | -20.4% | 0.59 |
| Zero slippage | 549 | 154 | 42.2% | 1.31 | +0.22R | 5.8% | -14.3% | 1.14 |
| Slippage $0.02 | 549 | 154 | 37.7% | 0.93 | -0.03R | -1.5% | -23.7% | -0.21 |
| **2x costs** | 549 | 154 | 37.7% | **0.84** | -0.10R | -3.4% | -29.4% | -0.58 |

Top 5 / 10 / 20 candidates per day give identical results (cash-bound). Years: the
five-pillar run loses in 2023 (-$1.9k) and 2024 (-$2.2k); the honest run loses $7.5k in
2024. Concentration: the five-pillar run's ten best trades are 278% of its profit (without
them -$6.6k); the honest run's total profit over five years is $502.

**Kill criteria:**

| Criterion | Result |
|---|---|
| Fewer than 300 trades | **Fail** for the five-pillar run (154); pass for the honest run (778) |
| Edge lives in one year | **Fail** -- 2022 carries the five-pillar run; the honest run is flat |
| Neighbourhood mostly positive | **Fail** -- half the cells are negative |
| Dies at 2x costs | **Fail** -- PF 0.84 |

**Verdict: not passed.** The mechanical Gap and Go has no measurable edge after costs on
five years of data. Whatever edge the course version has must live in the parts that are
not mechanical -- catalyst quality, tape reading, when to skip -- and those cannot be tested
here or handed to a bot. The two small-cap breakout entries at the open (§2b, §2c) are now
both measured: a real but cost-fragile signal (ORB) and no signal (Gap and Go).

## 2d. Third candidate, pre-registered 2026-09-22 -- A4 large-cap daily mean reversion

Why this next: both small-cap breakout entries died on slippage at $25k; large caps trade at
sub-cent spreads, daily-bar rules need one order a day at the close (no pattern-day-trader
issue, fits a cash account), and the five years of daily files cover every US stock with
delistings included -- a cross-sectional test the SPY baseline could not give. Rules are
fixed here before any run:

- Universe each day, from prior days only: close > $20, 20-day average dollar volume
  >= $50M, 200-day history available, no split in the trailing 30 days, common stock / ADR.
- Signal: close above the 200-day simple moving average (uptrend) and 2-day RSI < 10
  (short-term washout); rank by RSI ascending; take up to 5 names.
- Entry: buy at that day's close (the bot would send a market-on-close-style limit at 15:55).
- Exit: sell at the close of the first day whose close is above the prior day's high, or
  after 10 trading days, whichever first.
- Sizing: 20% of equity per name, at most 5 names; costs IBKR fixed + $0.01/share
  slippage each side (large-cap spreads are tighter; 1c stays for comparability).
- Kill criteria unchanged: < 300 trades, edge in one year, neighbourhood (RSI 5/10/15,
  hold 5/10/20, MA 100/200) not mostly positive, dies at 2x costs. Concentration is reported.

### Gate 1 result -- A4, 2026-09-22 (harness: `research/orb/build_daily.py`, `backtest_mr.py`)

Data: split-adjusted daily bars for every US stock, 2021-09-21 .. 2026-09-21 (13.9M rows,
20,757 tickers, delisted included); a held name whose bars end is closed at its last
print. Account as in §2b ($25k cash, IBKR fixed commission, $0.01/share slippage).

| Run | Signals | Trades | Win | PF | Per trade | CAGR | Max DD | Sharpe |
|---|---|---|---|---|---|---|---|---|
| **Pre-registered rule** ($20+, $50M ADV, > SMA200, RSI2 < 10, 5 names, 10-day hold) | 58,593 | 1,223 | 64.3% | **1.02** | +$1.93 | **1.75%** | **-31.7%** | 0.19 |
| RSI2 < 5 | 27,968 | 1,172 | 64.5% | 1.07 | +$7 | 5.9% | -24.9% | 0.36 |
| RSI2 < 15 | 88,035 | 1,235 | 64.0% | 1.00 | +$0 | 0.1% | -33.1% | 0.12 |
| Hold 5 / 20 days | | 1,558 / 1,136 | 62% / 65% | 0.99 / 1.04 | -$0.4 / +$3.8 | -0.6% / 2.5% | -31% / -30% | 0.09 / 0.22 |
| SMA100 trend | 48,485 | 1,220 | 64.0% | 1.14 | +$14 | 10.2% | -25.8% | 0.40 |
| No trend filter | 131,967 | 1,217 | 62.7% | 0.96 | -$3 | -3.2% | -56.6% | 0.10 |
| 3 / 10 names | | 748 / 2,408 | 64% / 65% | 1.00 / 1.04 | +$0.3 / +$1.9 | 0.1% / 2.9% | -39% / -29% | 0.13 / 0.25 |
| $10+, $20M ADV | 92,337 | 1,198 | 61.9% | 1.06 | +$5 | 4.5% | -44.2% | 0.30 |
| **$200M ADV (mega-caps)** | 24,067 | 1,214 | 65.7% | **1.19** | +$18 | **12.7%** | -23.5% | 0.66 |
| Zero / $0.02 / $0.03 slippage | | 1,223 | 64% | 1.04 / 1.00 / 0.99 | +$4 / +$0 / -$1 | 3.4% / 0.3% / -1.3% | -31% / -33% / -33% | |
| **2x costs** | | 1,223 | 64.0% | **1.00** | $0.00 | -0.1% | -32.6% | 0.11 |

Years (base): 2022 +$369, 2023 -$4,404, 2024 +$8,212, 2025 +$587, 2026 -$2,406. Ten best
trades = 476% of the profit; without them -$8,866. Months positive 28 of 51. Costs are
*not* the killer here (fees $2.5k over five years): the rule itself is flat in this period
on this universe, and its losses come from names that fall through the "washout" (CPRI
-52%, RVSN -46%, VKTX -30% held to the time stop).

**Kill criteria:** edge in one year -- **Fail** (2024 carries it); < 300 trades -- pass;
neighbourhood mostly positive -- **Fail** (half the cells at or under 1.0); dies at 2x
costs -- **Fail** (PF 1.00). **Verdict: not passed.**

**A4b, recorded, not promoted:** the same rule on mega-caps only ($200M+ ADV) is the one
robust cell -- PF 1.19, 12.7% CAGR, and it *survives* 2x costs (PF 1.17, 11.2%), 3 cents of
slippage (PF 1.15) and every neighbour (RSI 5/15, hold 5/20, SMA100, 10 names, $500M ADV:
PF 1.11-1.21). Years: 2022 +$33, 2023 +$5,248, 2024 +$7,894, 2025 +$231, 2026 +$7,994;
ten best trades 58% of profit; months positive 33 of 51. It is an in-sample universe pick
on five years, so it is not promoted from this run. It is the first cell of any candidate
that passed the cost test, and it is the shape of a strategy that fits a cash account:
one order a day at the close, in names with sub-cent spreads. Re-run it on the 30-year
survivor-biased S&P history for a directional out-of-sample check before deciding.

## 2e. Where this leaves gate 1 (2026-09-22, end of day) -- small-cap track

Three candidates, one day, one honest harness: the two small-cap open breakouts die on
cents of slippage at $25k, the mid/large-cap daily mean reversion is flat. The only
things that have passed anything are (a) the SPY swing rules, reproduced from a published
33-year record (§3), and (b) the A4b mega-cap cell, in sample. Both are daily-bar,
close-of-day, cash-account-friendly strategies -- the opposite of what Nova's desk was
built to watch, and the operator's definition of done (paper evidence, then a live test)
does not care which kind of rule makes the money.

**Operator direction (2026-09-22, evening): the bots are for small caps.** A5 (the SPY
swing rules) is parked, not run; the large-cap cell A4b stays recorded. What the small-cap
evidence says is not "no edge" but "the edge lives inside the costs": the ORB's relative-
volume ordering is real (§2b), its profit sits inside one to two cents per share of
slippage and inside ~10 trades, and the entry-bar fill is the one thing a minute bar cannot
settle. So the next work was about **fills and costs on small caps** -- S1 replayed the ORB on
one-second bars to settle the entry-bar fill, S2 was to measure the real cost on Paper, S3
pre-registered halt-resume and VWAP-reclaim rules. S1 ran the same night; what it found
changed the track.

### S1 result -- ORB on one-second bars (2026-09-22, night; `research/orb/backtest_orb_seconds.py`)

Same published rule, same `selection`, top 10 by opening relative volume; the 09:30-11:00
window replayed from `store/seconds.duckdb` (18,771 symbol-days, 32.0M one-second bars).
The fill is the first second at or after 09:35 whose high reaches the 5-minute high, at
max(second open, level) + slippage; the stop is checked every second after the fill (entry
second: only a close at or below the stop; later: the first low at or below it, filled at
min(second open, stop) - slippage); after 11:00 the position rides `minutes_selected` to the
stop or the close. Costs, sizing and cash reservation as §2b. Results as produced:
`results_orb_seconds_s1_2026-09-22.json`, `results_orb_seconds_robustness_2026-09-22.json`.

| Run ($25k, top 10) | Trades | Win % | PF | Exp (R) | CAGR | Max DD |
|---|---|---|---|---|---|---|
| Base, $0.01 slippage | 3,384 | 10.1 | 0.97 | -0.04 | -4.0% | -51% |
| $0 slippage | 3,385 | 10.9 | 1.08 | +0.12 | +9.4% | -33% |
| $0.02 slippage | 3,388 | 8.9 | 0.83 | -0.28 | -20.4% | -75% |
| $0.03 slippage | 3,385 | 8.2 | 0.73 | -0.53 | -33.4% | -88% |
| 2x costs | 3,388 | 8.8 | 0.79 | -0.35 | -25.2% | -80% |
| Stop 5% ATR | 3,387 | 5.0 | 0.75 | -0.42 | -15.6% | -60% |
| Top 5 | 2,229 | 9.2 | 0.95 | -0.06 | -3.6% | -43% |
| Paper's costs ($0.0035/sh, no minimum, no slippage) | 3,386 | 10.9 | 1.11 | +0.16 | +12.5% | -30% |

Pre-planned splits (base run, reported, never re-selected): ranks 1-5 2,229 trades at
-0.05R, ranks 6-10 1,155 at -0.02R; entries $2-10 275 trades at -0.05R, $10+ 3,109 at
-0.04R -- no bucket is positive. Exit reasons: 2,776 trades (82%) stopped on a one-second
low, 79 on the entry second, 165 on a minute bar after 11:00, and 364 (11%) rode to the
close at +10.0R on average (94% of those were winners). Half of the one-second stops fire
within 60 s of the fill (median 56 s); the median stop distance is $0.14 on a $35 median
entry -- 0.4% of the price. The ten best trades made +$24,069 on a -$4,550 total; the other
3,374 lost $28,620 between them. By year: 2022 +$9,283, every other year flat or negative.

**Verdict: not passed** -- three of four kill tests (negative at the base cost, dies at 2x
costs, profit inside ~10 trades; the neighbourhood is negative too). §2b's 26% CAGR was an
artefact of the minute-bar entry-bar rule, which could not see the lows that print between
a fill and the next minute's close: at one-second resolution the published 10%-ATR stop is
noise, and the rule is a 10%-win lottery ticket on the ride to the close. It was not a
fills-and-costs problem after all -- the stop is the problem, and §2b's grid already showed
a wider stop does not rescue it. The run also states one thing plainly: the `selection`
universe has a median entry price of $35 and only 8% of its trades under $10 -- "stocks in
play" by relative volume is not the operator's small-cap universe.

### Disposition of S2 and S3 (2026-09-22, night)

- **S2 dropped.** The ORB bot pack on Paper existed to measure the real slippage of a rule
  that was alive at one cent. It is not; measuring the cost of a dead rule proves nothing.
- **S3 shelved to last** (operator: "there is a halt strategy but ... it's just the hardest
  one"). Halt-resume stays pre-registered as written above and is the last small-cap rule to
  run. VWAP reclaim is folded into the private catalogue (S4) -- it is one of the taught setups.

### S4 -- the operator's strategy catalogue (operator ask, 2026-09-22, night)

The operator asked that every momentum setup they trade by hand be written up first, then
one chosen together to master. The source material and the catalogue stay **off this
repository**, on the desk's F: drive (operator instruction, 2026-09-22: the material stays
private; the chosen strategy itself may be recorded here). This note records only that the
step exists and what closes it. The vault's older summaries (`Candidate-Strategies-for-Nova.md`, the backbone's pillars) are
claims to check against the private material, not evidence -- the operator
flagged them as possibly wrong.

Done when: the catalogue lists every setup as a rule sheet -- universe, setup, entry, stop,
target, management, time of day, as the operator trades it -- marks which are mechanical enough to pre-register on the store and
what each needs that the store lacks (Level 2, the tape, news quality, halts), and ends in a
ranked shortlist the operator chooses from. The chosen rule is then pre-registered in this
note as Nova's own and run through the same kill tests on its own universe (with the float
pillar's survivor bias stated).

- **Cash account, stated once:** T+1 settlement means today's buying power is yesterday's
  settled cash; the bot sizes from settled cash (Nova's practice broker enforces buying
  power, live IBKR enforces settled funds), and there is no pattern-day-trader limit on a
  cash account. Long-only throughout; shorts stay behind the parked Phase K.

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
| 2026-09-22 | **Gate 1 verdict for A2 Gap and Go: not passed** (PF 1.00 without the survivor-biased float pillar; fails three of four kill tests). Not promoted. **Next candidate: A4 large-cap daily mean reversion**, rules pre-registered in §2d. L1 data complete; the Massive plan may be cancelled. | Claude Fable 5.1 for the operator |
| 2026-09-22 | **Gate 1 verdict for A4: not passed** (PF 1.02, 2024 carries it, dies at 2x costs). A4b mega-cap cell recorded as the first cost-robust cell (PF 1.19, survives 2x costs) but in-sample -- not promoted. **Next: A5 SPY swing rules through the kill tests, then a daily-bar bot pack for paper** (§2e). | Claude Fable 5.1 for the operator |
| 2026-09-22 | **Operator direction: small caps only** ("I want to focus on small cap stocks for my bots"). A5 parked unrun. Next is the small-cap track of §2e: S1 ORB on one-second bars, S2 the ORB bot pack on Paper to measure real slippage (the go/no-go is the measured cost), S3 halt-resume and VWAP-reclaim rules pre-registered on the same store. | Operator |
| 2026-09-22 | **S1 verdict: not passed.** The ORB on one-second bars: PF 0.97 at 1c, 0.83 at 2c, 82% of trades stopped on a one-second low and half of those inside 60 s -- the published 10%-ATR stop is 0.4% of a $35 median entry, and §2b's minute-bar result was the entry-bar rule hiding intrabar stop-outs. **S2 dropped** (nothing alive to carry to Paper). | Claude Fable 5.1 for the operator |
| 2026-09-22 | **Operator: halts last; learn every setup in the private material first, then choose one to master together.** S3 halt-resume shelved to last. **S4** -- the catalogue (rule sheets with citations, mechanical-or-not, a ranked shortlist) is written off-repo on F:; the operator picks the first strategy to master. The vault's older summaries are not trusted. **Operator instruction, same night: the source material and the catalogue stay private on F:, off the public repo; the chosen strategy itself may be recorded here.** | Operator |
