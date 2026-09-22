# Momentum setups -- gate 1 harness (Phase L, section 2f)

Minute-bar screens of three small-cap momentum setups on the Five Pillars universe built by
`research/orb/select_gng.py --no-float` (`gng_selection_nofloat`), with 04:00-16:00 minute bars
extracted into `minutes_pillars` by
`py -3 research/orb/extract_minutes.py --selection gng_selection_nofloat --table minutes_pillars --start 04:00`.
Research only: nothing here is imported by `backend/` and nothing places orders. Rules,
pre-registration and results: `knowledge/obsidian/03-Nova-Decisions/Bot-Trading-Plan.md` section 2f.

| Command (repo root) | Setup |
|---|---|
| `py -3 research/momentum/backtest_setups.py --tag fp_base --ladder` | P1 first / second pullback |
| `py -3 research/momentum/backtest_setups.py --set setup=flat_top --tag ft_base --ladder` | P2 high-of-day / flat-top breakout |
| `py -3 research/momentum/backtest_setups.py --set setup=red_to_green --tag r2g_base --ladder` | P3 red to green |

Every free number is a `Params` field (`--set field=value`); `--ladder` runs the pre-registered
neighbourhood and writes `store/robustness_<tag>.json`. Fills, costs, sizing and the cash
account follow `research/orb/backtest_orb.py`; the entry bar's stop counts only on a close at
or below it (the minute-bar optimism S1 measured), so a passing screen would still need its
trades settled on one-second bars. `results_*_2026-09-22.json` are the runs as produced:
none passed.
