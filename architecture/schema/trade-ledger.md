# Data schema: The author's trade ledger

Part of `AGENTS.md` §3 (Data Schema), which indexes every file in this folder. Owner: the S7 study,
`knowledge/obsidian/03-Nova-Decisions/Bot-Trading-Plan.md` §2h. No repo code reads or writes it yet. Same law as the
constitution: a wire or persisted shape changes here first, in the same commit as the code (Invariants #1 and #5).

## The ledger (S7, operator ask 2026-10-11)

"if he makes money, we should be able to make money too" -- a record of the trades the operator's material's author
actually took, read from the operator's private video archive (daily recaps and live sessions; never course lessons).
The files live only on the desk's F: drive, under `F:\Nova\ledger\<run>\` (the pilot's run is `pilot`). They never
enter this repository (operator instruction, 2026-09-22). The desk never reads them. Research code that does reads
only `schema_version: 1` and refuses any other version.

- **`selection.json`**, written before any video is transcribed: `{schema_version: 1, rule, selected_at, days: [{date,
  videos: [{file, kind: "recap" | "live"}], checked_with: "trades_v1" | "minute_aggs_v1"}]}`.
- **`trades.jsonl`**, one line per trade: `{schema_version: 1, trade_id: "<date>-<TICKER>-<n>", date, ticker, side:
  "long" | "short", fills: [{kind: "entry" | "add" | "exit", time_et: "HH:MM:SS" | null, price, shares, source}],
  stated_pnl, setup_named, sources: {<field>: [source]}, verification: {status: "pinned" | "price_only" | "unmatched"
  | "unchecked", checked_with: "trades_v1" | "minute_aggs_v1", match: {kind: "print", time_et, price, size} | {kind:
  "bar", minute_et, o, h, l, c, v} | null, price_tolerance, minutes}, notes}`.
- **`days.jsonl`**, one line per selected day: `{schema_version: 1, date, videos: [{file, kind}], stated_day_pnl,
  summed_trade_pnl, reconciled, trades, sources: {<field>: [source]}, notes}`.
- A **`source`** is `{video, t, via: "transcript" | "still"}`: the video file, the second into it, and whether the value
  was heard or read off the screen.

Rules:

- **null means the author did not give it.** Every value the author states cites where it came from. A fill cites its
  own `source`. Every other stated field (`ticker`, `side`, `stated_pnl`, `setup_named`, `stated_day_pnl`) has an entry
  in `sources` under its own name. Market data never fills one in.
- `date` is the trading day and `time_et` is Eastern time. Prices and P&L are dollars. P&L is as the author states it,
  gross unless the author says otherwise. A day the author sat out has `stated_day_pnl: 0` and no trades.
- A trade seen in two videos is one row whose fills and `sources` cite both.
- `verification` is written only by the check against the Massive flat files (`backend/sim/massive_files.py`):
  - **pinned:** a price-setting print within `price_tolerance` of the first entry price, within `minutes` of its
    time. The tolerance is max(0.02, 0.5% of that price) and `minutes` is 2. On a `minute_aggs_v1` day, the price
    must fall inside a bar's low-high, widened by the tolerance. `match` holds the print or the bar that pinned it.
  - **price_only:** such a print or bar exists that day between 04:00 and 20:00 ET, but not in the window, or no time
    was given. `match` holds the one nearest in time.
  - **unmatched:** no such print or bar that day. `match` is null.
  - **unchecked:** the author gave no entry price, or the day has no Massive file. `match` is null.
  - Only pinned trades count toward the pilot's pinned rate; every other status counts against it.
- `summed_trade_pnl` is the day's trades' `stated_pnl`, or, where that is null, the P&L computed from their stated
  shares and prices.
- **reconciled** means `summed_trade_pnl` is within 20% of `stated_day_pnl`, or within $500 when `stated_day_pnl` is
  under $2,500 either way. It is false when the author states no day P&L.
- `report.md` beside them reads the run out against §2h. It is prose, not a schema.
