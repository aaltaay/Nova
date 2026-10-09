# The five-year test of the short setups (ADR 049 section 12)

Each short setup's On stays locked until its five-year test passed on the rules of its template in play. These
scripts are that test. They run on the desk, on the operator's Massive minute files, and write the result file the
setup's card and its On lock read (`backend/setup_scanner/short_tests.py`). Nothing here places an order, touches a
Nova account or changes a setting, and no agent writes a result file by hand.

The rules under test are the scanner's own: `test_shorts.py` imports the backend's detectors and scoring
(`setup_scanner/`) and builds the template in play exactly as a lane does. Every fixed number (the universe, costs,
size, the kill criteria, the neighbourhood, the permutation) is in `shorts_config.py` and pre-registered in ADR 049;
changing one is a new `HARNESS_VERSION`.

## Before the first run

- The minute files under `NOVA_MARKET_DATA_DIR` (default `E:\Nova\massive`), as gate 1 read them.
- The day movers index (ADR 050, `research/movers/README.md`), built over the five years:
  `py -3 research/movers/build_movers.py`.

## Run it (repo root)

| Step | Command | Produces |
|---|---|---|
| 1 | `py -3 research/shorts/select_shorts.py` | `shorts_selection` in `<NOVA_MARKET_DATA_DIR>\store\orb.duckdb`: every stock-day the scanner would have followed, with yesterday's SSR |
| 2 | `py -3 research/orb/extract_minutes.py --selection shorts_selection --table minutes_shorts --start 04:00` | `minutes_shorts`: the 04:00-16:00 minute bars of those stock-days |
| 3 | `py -3 research/shorts/test_shorts.py --setup <setup>` | `<NOVA_MARKET_DATA_DIR>\research\short_tests\<setup>.json` |

Step 3 runs once per setup: `backside_lower_high`, `bear_flag`, `failed_breakout`, `lost_vwap`, `ssr_bounce`.
`--template ID` tests another template than the one in play; `--workers N` sets the processes (default: the CPU
count less two). Steps 1 and 2 are needed once, and again when the index or the files grow (step 2 extracts only
the days it has not).

A look without a result file: `py -3 research/shorts/test_shorts.py --setup bear_flag --dry-run --days 20`.

## What a run does

- **The universe**, with no hindsight: a common stock at $1-$20 at +10% over its prior close, followed from the
  minute after both its +10% and its 100,000th share; likely splits left out. For the SSR bounce, yesterday's movers
  are followed from 04:00 (Former Momo).
- **The walk**: each minute's open and then its extreme (the low; the high for the SSR bounce) are fed to the
  detector as the live price, the minute closes, and the scoring takes the trade out by its own exits. One trade at
  a time on a stock.
- **SSR**: today's from the minute lows, yesterday's from the index. The four breakdown shorts are judged on their
  SSR-off triggers; their SSR days are reported apart (`ssr_days`), because minute bars cannot say whether a short
  above the bid would have filled.
- **The account**: gate 1's ($25,000 compounding daily, 1% risk a trade, at most 25% of equity, $500 minimum,
  IBKR's fixed commission, one cent of slippage on every fill).
- **The fixed-size readout** (`fixed_size`, harness version 2): the same trades on a fixed $25,000 that never
  moves. A losing run shrinks the compounding account until later triggers fall under the $500 minimum and are
  skipped; on the fixed account every trigger in the window is scored, by year. It is a readout only: the verdict
  reads the compounding account (ADR 049 amendment, 2026-10-09).
- **The verdict**: at least 300 trades; positive with the best year removed; a profit factor over 1 at twice the
  costs; a neighbourhood more than half positive; and a permutation p of 0.05 or less (1,000 seeded shuffles of each
  trade's entry to a random minute of its own day, inside the window).

The result file says `running` with its progress first and the verdict last, each written through a temporary file
and a rename. Its shape is in `architecture/schema/short-selling.md` ("The five-year test and the On lock"). A
result passes the lock only while its `rules.rules_hash` equals the template in play's `params_hash`: edit the
template and the setup tests again.

## Files

| File | Purpose |
|---|---|
| `shorts_config.py` | the fixed numbers, the neighbourhoods, the stated assumptions, the paths |
| `select_shorts.py` | step 1 |
| `short_sim.py` | the walk, gate 1's costs and account, the statistics, the permutation |
| `test_shorts.py` | step 3: the rules, the criteria and the result file |

Tests: `backend/tests/test_short_harness.py`.
