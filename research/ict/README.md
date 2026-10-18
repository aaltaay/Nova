# A6: the "one trade a day" sweep and fair value gap on SPY / QQQ

Offline test of a YouTube trader's strategy, as she teaches it, on the index ETFs (the market it was built for).
Rules, result and verdict: `knowledge/obsidian/03-Nova-Decisions/Bot-Trading-Plan.md` section 2i. Research only:
nothing in `backend/` imports this and nothing here places an order.

| Step | Command (repo root) | Produces |
|---|---|---|
| 1 | `py -3 research/ict/extract.py` | `E:\Nova\massive\store\ict_minutes.parquet`: SPY and QQQ 04:00-20:00 minute bars, every day on disk (about 15 minutes; re-runs skip days it has) |
| 2 | `py -3 research/ict/backtest.py` | `results_2026-10-18.json` here (base, side and symbol split, cost ladder, neighbourhood, kill criteria) and `ict_trades_base.csv` in the store (about 6 minutes) |
| test | `py -3 -m pytest research/ict/test_rules.py -q` | the rules on hand-built bars |

`rules.py` holds the rules as pure functions (hourly swing levels known before 09:30; sweep, shift, gap, limit order,
stop / target / 11:00 exit). `backtest.py` sizes and charges each fill like `research/orb/` ($25,000, 1% risk capped
at 2x equity notional, IBKR fixed $0.005/share min $1, $0.01/share slippage on every fill).

Verdict (2026-10-18): **not passed** -- 324 trades, profit factor 0.94, -0.01R a trade before costs.
