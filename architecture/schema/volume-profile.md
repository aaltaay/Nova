# Data schema: Volume profile

Part of `AGENTS.md` §3 (Data Schema), which indexes every file in this folder. Owners: `backend/volume_profile/`,
`frontend/src/volume_profile/`. Same law as the constitution: a wire or persisted shape changes here first, in the
same commit as the code (Invariants #1 and #5).

## Volume profile on the 5-minute chart (ADR 058, operator decision 2026-10-17)

How much traded at each price, drawn on the Trader's 5-minute pane only: **today's** profile from an anchor (09:30 ET
unless the operator drags it) to now, and **yesterday's** regular session (09:30-16:00 ET of the exchange day before).
Each has a point of control (the busiest row), a value area holding 70% of its volume (VAH on top, VAL below) and a
400-row histogram. Built from IBKR's 1-minute bars, never from the 5-minute candles it is drawn over. It is a chart
study: nothing here places, stages or blocks an order, and nothing feeds a scanner row, HOD Momo, a setup or a bot.

### The switch

The toolbar's **Profile** button on the Trader grid shows or hides it, for every Trader tab and window. It is off
until the operator turns it on (decision D1). The choice is the browser's own setting,
`localStorage["nova.volumeProfile.shown.v1"]`: `"1"` on, anything else off; a window hears another's change through
the `storage` event. While it is off the desk asks the backend nothing and draws nothing.

### `GET /api/volume-profile/{symbol}`

Query:

| Param | | Meaning |
|---|---|---|
| `kind` | `today` \| `yesterday` | Which profile. Required. |
| `day` | `YYYY-MM-DD` | The exchange day the pane calls today: the ET date of its last candle. Missing: the last exchange day on the wall clock. `yesterday` is the exchange day before it (`sim.trading_day.last_open_day`). |
| `anchor` | epoch seconds | `today` only: where the profile starts. Missing: `day` 09:30 ET. Must fall inside `day` 04:00-20:00 ET, else 422. |

Answer (200):

```json
{
  "schema_version": 1, "enabled": true, "symbol": "AAPL", "kind": "today", "day": "2026-09-30",
  "from": 1790861400, "to": 1790892000, "source": "bars_1m", "feed": "ibkr", "bars": 195,
  "row_size": 0.0234, "low": 330.14, "high": 339.5, "total_volume": 18690000,
  "poc": 337.36, "vah": 339.29, "val": 336.6, "poc_row": 308, "vah_row": 391, "val_row": 276,
  "histogram": [[330.14, 4100, 9800], "... [row's low price, up volume, down volume] x rows, lowest first"],
  "filling": false, "error": null
}
```

- `from` / `to`: the stretch measured, epoch seconds, `[from, to)`. `today`'s `to` is `day` 20:00 ET; it holds the
  minutes the store has so far.
- `source`: `bars_1m` -- 1-minute bars. A bar's volume is spread evenly over the rows its high-low range covers. `up`
  is volume on bars that closed at or above their open, `down` the rest: colour only, never buyers vs sellers.
- `feed`: who drew those bars -- `ibkr` (the chart store or an IBKR request), `massive` (the operator's Massive files,
  on a Massive Sim replay), `capture` (a Session Record's replay). The desk names a feed other than IBKR on the
  profile's tab.
- Rows: 400 over `low`-`high`, never thinner than $0.01. The POC is the busiest row (a tie goes to the row nearest
  the middle); the value area grows from it two rows at a time toward the heavier side until it holds 70%. `poc` is
  the POC row's middle, `vah` the value area's top, `val` its bottom.
- **No profile** is a stated empty, never a zero: `histogram: []`, the price fields `null`, `error` in words. With
  `filling: true` the desk asks again in `VP_RETRY_MS` (yesterday's bars are being read from IBKR, or IBKR's budget
  said not now).
- On a Sim replay desk (`sim.mode.is_replay_desk()`) the profile reads the replay's bars, never live ones (below).

### Where the bars come from

- **Today:** the chart store (`bars_store`, timeframe `1Min`), which the Trader's 1-minute pane fills. No IBKR request.
- **Yesterday:** the chart store when it holds at least `VP_SESSION_MIN_BARS` of that session's minutes (a chart of the
  stock was open that day). Otherwise one paced IBKR request (`volume_profile/ibkr_minutes.py`): 1-minute TRADES bars,
  regular hours, `23400 S` ending 16:00 ET that day, in `historical_service`'s one budget -- shed while an open chart
  loads, while pacing asks for a wait, or with `IBKR_HISTORY_TRADING_RESERVE` or fewer requests left of the 10
  minutes. Those bars are not stored. The finished profile is kept in memory, per symbol and day, up to
  `VP_CACHE_MAX` of them; a restart reads them again. Nothing is persisted.

### On a Sim replay (ADR 058 amendment, operator report 2026-10-17)

One feed, whatever drew the replay: the profile reads what the replay's chart reads.

- **Today:** the replay's own 1-minute bars (`sim.chart_replay.fetch_replay_bars`, the 5-minute pane's own source):
  a Massive window's minutes, a Session Record's, or the store's for that day -- finished bars only, none after the
  playhead. `feed` says which. Never cached: the playhead moves. The desk drops today's profile the moment the
  playhead is scrubbed (`nova:sim-clock-scrub`) and asks again, so no bar from after it is ever drawn.
- **Yesterday, on a Massive replay of this stock:** the exchange day before's regular session from the same Massive
  files (`volume_profile/massive_minutes.py` through `sim.massive_files`: that day's `minute_aggs_v1` file, the
  ticker's rows unaltered -- as traded, like the replay itself). A file without its seek index is streamed from the
  start, which can take a while: the answer is `filling` until the read is done (one read per stock and day, in a
  worker thread), then kept in memory like an IBKR one. The day's file not on disk is a stated empty.
- **Yesterday, on any other replay** (an IBKR download, a Session Record, another stock than the Massive window's):
  as live -- the chart store, else the one paced IBKR request -- since those replays' bars are IBKR's.
- At the live edge (`live_edge`) the Sim desk reads the live feed, as Paper does.
