# Data schema: Ahead

Part of `AGENTS.md` §3 (Data Schema), which indexes every file in this folder. Owners: `backend/ahead/`,
`frontend/src/ahead/`. Same law as the constitution: a wire or persisted shape changes here first, in the same
commit as the code (Invariants #1 and #5). The wire is written four times and the four must agree: here,
`frontend/src/ahead/aheadTypes.ts`, `backend/ahead/view.py` and the golden answers in
`frontend/src/ahead/__fixtures__/` (one per state, read by both Vitest and pytest's `test_ahead_wire.py`).

## Ahead on the 1-minute chart (ADR 065, operator decision 2026-10-20)

The next 15 minutes as a private forecaster sees them, drawn in a hatched zone right of the newest completed candle
on the Trader's 1-minute pane, beside Nova's own support and resistance lines carried on to where they meet. A
forecast is never data: the zone is hatched and labelled "AI view, not data", every number from the forecaster is
marked as a forecast, and nothing is added to any chart series. It is a chart study: nothing here places, stages,
sizes, delays or blocks an order, and nothing feeds a scanner row, a setup, an alert or a bot.

The backend serves only what needs the forecaster. The lines to the meet, the walls, the odds and the MACD fan are
worked out on the desk (below) from the answer, the stock read the Trader page already holds
(`read.level_map.lines.one_minute`, `read.level_map.intraday`, `read.setups`, `read.followed`,
`read.followed_note`) and the chart's own candles.

### The switch

The Trader toolbar's **Ahead** button shows or hides it, for every Trader tab and window. Off until the operator turns
it on. The choice is the browser's own setting, `localStorage["nova.ahead.prefs"]`, a `prefStore` envelope
(owner `frontend/src/ahead/aheadPrefs.ts`):

```json
{"schema_version": 1, "value": {"shown": false, "scope": "all", "unearned": false}}
```

| Field | Values | Meaning |
|---|---|---|
| `shown` | boolean, default `false` | The toolbar switch. While off the desk asks nothing and draws nothing. |
| `scope` | `all` \| `lines` \| `flat_top` \| `first_pullback`, default `all` | The Ahead panel's segments. `lines` draws Nova's lines only, with no AI view. |
| `unearned` | boolean, default `false` | "Show before it has earned it": draw the AI view although the forecaster has not passed its exam. |

A missing or unreadable value, or another `schema_version`, reads as the defaults. A window hears another's change
through the `storage` event. Which sheet is open and the answers themselves live in memory only
(`aheadStore.ts`); nothing else is persisted, on the desk or in the backend.

### `GET /api/ahead/forecast/{symbol}`

`symbol` is upper-cased and must match `[A-Z][A-Z0-9.\-]{0,9}`, else 422
`{"detail": {"reason": "AHEAD_BAD_SYMBOL", "error": "<words>"}}`. Every other outcome is 200 with an answer whose
`ai.state` says what happened. The route answers at once and never waits on the forecaster: the first ask for a
minute answers `pending` and the desk asks again.

Answer (200, `ai.state: "ready"`; the made-up ticker and numbers of `answer_ready.json`, arrays shortened):

```json
{
  "schema_version": 1, "symbol": "XYZ", "generated_at": 1792500065, "replay": false, "venue": "paper",
  "bar_t": 1792500000, "as_of": 1792500060,
  "bars": {"n": 240, "contiguous_tail": 240, "tail_gap_sec": 0},
  "price": 4.62, "prior_close": 3.1, "volume_last15": 120000,
  "ai": {
    "state": "ready", "reason": null, "need": null, "have": null, "retry_ms": null, "retry_at": null,
    "model": {"name": "model-a", "version": "1.0"},
    "exam_passed": false,
    "exam": {
      "passed": false, "as_of": "2026-10-21", "summary": "Example only: a made-up exam for tests.",
      "scope": "Example only: made-up scope.",
      "volume": {"model": {"spearman": 0.5, "miss_x": 2.0}, "baseline": {"name": "time-of-day", "spearman": 0.6, "miss_x": 1.9}},
      "range": {"model": {"spearman": 0.3, "miss_x": 1.8}, "baseline": {"name": "time-of-day", "spearman": 0.35, "miss_x": 1.7}},
      "band80_coverage": 0.79, "sample": {"days": 10, "moments": 100}
    },
    "horizon_min": 15, "step_sec": 60,
    "levels": [0.1, 0.25, 0.5, 0.75, 0.9],
    "close": [[4.5963, 4.6075, 4.62, 4.6325, 4.6437], "... 15 rows"],
    "volume": [[3600, 5600, 8000, 11200, 16800], "... 15 rows"],
    "paths": {"n": 16, "close": [[4.6153, 4.6247, "... 15 closes"], "... n rows"], "joined_by": "gaussian-copula"},
    "volume_15": [60000, 90000, 120000, 170000, 240000],
    "range_15": [0.01, 0.015, 0.02, 0.03, 0.04],
    "compute_ms": 210, "issued_at": 1792500064
  },
  "never": "A forecast only: nothing here places, blocks, sizes or delays an order."
}
```

Units: times are epoch seconds; shares and coverage are fractions 0-1; prices are dollars, rounded to 4 decimals (6
below $1); volumes are whole shares.

| Field | Null when | Meaning |
|---|---|---|
| `generated_at` | never | The desk clock when answered: the playhead on a replay desk, else the wall clock. Always `>= as_of`. |
| `replay` | never | `true` on a Sim replay desk (`sim.mode.is_replay_desk()`; an error there counts as a replay). |
| `venue` | never | `live` \| `paper` \| `sim`, the desk's venue. |
| `bar_t` | no candles | Start of the newest completed 1-minute candle sent. |
| `as_of` | no candles | `bar_t + 60`: the end of that candle, where the forecast starts. Never later than the desk clock. |
| `bars.n` | never | Completed candles of today's session (04:00 ET on) that were sent; `0` with none. |
| `bars.contiguous_tail` | never | How many of the newest candles are consecutive minutes. |
| `bars.tail_gap_sec` | no candles | The desk minute minus `as_of`. |
| `price` | no candles | The newest completed close (real). |
| `prior_close` | Nova does not know it | The previous session's close, read from its owner (the replay's own on a Sim replay); never derived from a percentage. |
| `volume_last15` | no candles | Real volume of the candles that closed in the last 15 minutes. |
| `ai.state` | never | One of the states below. |
| `ai.reason` | `ready` | Plain words whenever the state is not `ready`. |
| `ai.need`, `ai.have` | not `not_enough_bars` | Candles needed (30) and candles held. |
| `ai.retry_ms` | not `pending` | Ask again after this many milliseconds (1000). |
| `ai.retry_at` | unless the breaker is open (`offline` after 3 misses in a row); a single `offline` answer has none | When Nova asks the forecaster again, epoch seconds on the wall clock (also on a Sim replay: the breaker counts real seconds). `reason` says "asks again in N s". |
| `ai.model` | unknown | `{name, version}` from the forecaster. |
| `ai.exam_passed` | not `ready` | The forecaster's own verdict, from its answer. |
| `ai.exam` | no exam has run, or the health is unknown | The forecaster's exam from its health (below). `scope` may be `null`. |
| `ai.horizon_min`, `ai.step_sec` | never | `15` and `60`. |
| `ai.levels` | not `ready` | Always exactly `[0.1, 0.25, 0.5, 0.75, 0.9]`. |
| `ai.close`, `ai.volume` | not `ready` | `horizon_min` rows (minute 1 first), one column per level, each row ascending. Prices `> 0`, volumes `>= 0`. |
| `ai.paths` | not `ready` | `n` (16 or more) rows of `horizon_min` closes, and `joined_by`: how the per-minute ranges were joined into paths. Volume paths are not sent. |
| `ai.volume_15` | not `ready` | The next 15 minutes' total volume, one value per level, ascending. |
| `ai.range_15` | not `ready` | The next 15 minutes' (high - low) / last close, one value per level, ascending. |
| `ai.compute_ms` | not `ready` | The forecaster's own compute time. |
| `ai.issued_at` | not `ready` | When Nova received the answer. |
| `never` | never | The chart-study sentence. |

**A non-ready answer carries no forecast numbers:** `levels`, `close`, `volume`, `paths`, `volume_15`, `range_15`,
`compute_ms`, `issued_at` and `exam_passed` are `null` whenever `ai.state` is not `ready`. `model` and `exam` may
still be present, from the forecaster's health.

States (`ai.state`). The backend checks, in this order (`backend/ahead/service.py`): no completed candle, not set
up, a candle ending after the desk clock, fewer than 30 candles, quiet, the breaker, then the kept answer for this
minute (a forecast, or a failure younger than 5 s), else it asks and answers `pending`.

| Step | State | When | Forecaster asked? |
|---|---|---|---|
| 1 | `not_enough_bars` | No completed candle today (`have: 0`, `bar_t`, `as_of` and `price` null). | No |
| 2 | `not_set_up` | `NOVA_AHEAD_URL` or `NOVA_AHEAD_TOKEN` is unset or refused (below); `reason` says which. | No: no request leaves Nova |
| 3 | `error` | A candle that ends after the desk clock (fails closed). | No |
| 4 | `not_enough_bars` | Fewer than 30 completed candles (`need: 30`, `have: n`). | No |
| 5 | `quiet` | The newest candle ended more than 120 s before the desk minute: no trade lately. | No |
| 6 | `offline` | After 3 misses in a row Nova stops asking for 30 s; `retry_at` says when it asks again. | Not until `retry_at` |
| 7 | `ready` | The forecast kept for this minute. | Already asked |
| 7 | `offline`, `warming`, `error`, `not_enough_bars` | The failure kept for this minute (5 s): no answer in time or no connection (`offline`, no `retry_at`); the forecaster is starting up (503 or its health: `warming`); anything Nova cannot use -- a refused token, another HTTP status, a body over 512 KB or not JSON, a contract mismatch, a missing or out-of-shape field named in `reason`, or the ask itself failing (`error`); the forecaster's own 409 (`not_enough_bars`). | Already asked |
| 8 | `pending` | Nothing kept: the ask for this minute is in flight (one per symbol). | Yes, once |

How the backend asks (`backend/ahead/service.py`):

- The desk clock is read once per request. On a replay desk it is the playhead (`stock_read.replay_read.playhead()`),
  and the bars are the replay's own (`stock_read.replay_read.bars`); otherwise the wall clock and the chart store's
  1-minute bars (`sensors.feeds.get_bars`), keeping only bars with `t + 60 <= now`. Then today's session only
  (`stock_read.indicators.session_of`). Ahead never opens an IBKR line and never asks IBKR for history.
- A success is kept per `(symbol, as_of, venue, number of bars, last close, last volume)`, up to 64; that minute is
  never asked twice. A failure (`offline`, `warming`, `error`) is kept only 5 s, then asked again.
- One ask in flight per symbol; the newest minute wins and nothing is queued. The forecaster is asked on Ahead's own
  two-thread pool, never the pool that reads the bars.
- The forecaster's health is trusted 15 s when ready, 5 s otherwise.
- The prior close is read from its owner: on a replay, the loaded replay's own (`sim.history_playback` /
  `sim.capture_player`, resolved by `sim/prior_close.py` when it loaded); otherwise the scanner board row, then the
  Level 1 line's previous close (`strategy.symbol_pillars`). Unknown is `null`.
- `backend/ahead/` imports only its allow-list (`constants_ahead`, `http_pool`, `requests`, `fastapi`,
  `scanner_wire`, `sensors.feeds`, `stock_read.replay_read`, `stock_read.indicators`, `sim.mode`,
  `sim.history_playback`, `sim.capture_player`, `strategy.symbol_pillars`) and never the stock read's routes; no
  money-path package imports it (`backend/tests/test_ahead_boundaries.py`).

### `GET /api/ahead/status`

Is a forecaster set up, and what its health says (the Ahead panel's exam and report cards).

```json
{
  "schema_version": 1, "configured": true, "reason": null, "checked_at": 1792500065,
  "health": {
    "state": "ready", "detail": null, "contract_ok": true,
    "model": {"name": "model-a", "version": "1.0"},
    "exam": {"passed": false, "as_of": "2026-10-21", "summary": "...", "scope": "...", "...": "as in the answer"},
    "live": {"since": "2026-10-21", "scored": 12, "volume_spearman": 0.4, "range_spearman": null, "band80_coverage": 0.75}
  }
}
```

- `configured: false`: `reason` says why (`status_not_configured.json`) and `health` is `null`; nothing is asked.
- `health.state`: `ready` \| `warming` \| `error`; `detail` in words when not ready. `health` is `null` whenever the
  forecaster is unreachable, its health is malformed or it speaks another contract, and `reason` says why (for
  example "contract mismatch: ..."); so `contract_ok` is always `true` when `health` is present.
- `health.live`: the forecaster's own score of its forecasts once the 15 minutes they cover have closed. A score not
  yet made is `null` -- the desk shows "— not scored yet", never a zero.

### The forecaster contract (`ahead-forecaster/1`)

The private forecaster is a separate program on this PC. Nova is its only caller and its only source of bars; it
reads no market data, places nothing and writes nothing into Nova's folders. Only the wire is described here.

- **Transport:** HTTP/1.1 JSON on loopback. `NOVA_AHEAD_URL` (`http(s)`, host `127.0.0.1`, `localhost` or `::1`;
  anything else is `not_set_up`, "NOVA_AHEAD_URL must name this PC (127.0.0.1)"). Every request carries
  `Authorization: Bearer <NOVA_AHEAD_TOKEN>`; the token is never logged, proxies from the environment are not used
  and redirects are not followed. Timeouts: health 1 s, forecast 3 s. Answers over 512 KB are refused.
- **`GET /v1/health`** answers `{contract: "ahead-forecaster/1", state: "ready" | "warming" | "error", detail,
  model: {name, version, ...}, exam, live}`. `exam` is `null` until one has run, else
  `{passed, as_of, summary, scope, volume: {model: {spearman, miss_x}, baseline: {name, spearman, miss_x}}, range:
  (same), band80_coverage, sample: {days, moments}}`; `scope` is a sentence naming what kind of stocks and hours
  the exam covered (missing reads as `null`). `passed` is the forecaster's own verdict; Nova does not judge it
  again. `live` is `{since, scored, volume_spearman, range_spearman, band80_coverage}` with nullable numbers, and
  counts only forecasts asked with `venue` `live` or `paper`: Sim requests are never in it.
- **`POST /v1/forecast`** request:

  ```json
  {"symbol": "XYZ", "as_of": "2026-10-21T09:01:00-04:00", "horizon_min": 15, "prior_close": 3.1, "venue": "paper",
   "bars": [{"t": "2026-10-21T08:05:00-04:00", "o": 4.5, "h": 4.56, "l": 4.49, "c": 4.55, "v": 12000}]}
  ```

  `bars` are today's completed 1-minute bars from 04:00 ET, oldest first, `t` the bar's start in ET with its offset;
  a minute with no trade is left out, never invented. `as_of` is the end of the last bar, on the desk clock.
  `prior_close` may be `null`; the forecaster takes it as unknown and invents none.
- **Answer (200):** `{contract, symbol, as_of, horizon_min, model, levels, close, volume, paths: {n, close, volume,
  joined_by}, volume_15, range_15, exam_passed, compute_ms}`. Nova checks, and answers `error` naming the field
  otherwise: the contract string; `symbol` echoed; `as_of` echoed as the same instant; `levels` exactly the five
  above (within 1e-9); `close` and `volume` `horizon_min` rows of five finite numbers, each row non-decreasing,
  closes `> 0`, volumes `>= 0`; `paths.n >= 16` and `paths.close` `n` rows of `horizon_min` finite closes `> 0`;
  `volume_15` and `range_15` five values, non-decreasing, `>= 0`; `exam_passed` a boolean.
- **Other answers:** 401 (missing or wrong token) is `error`, "the forecaster refused Nova's token"; 409
  `{"error": "NOT_ENOUGH_BARS", "need": 30}` is `not_enough_bars`; 503 `{"error": "WARMING"}` is `warming`; any other
  status is `error` with the code; a timeout or no connection is `offline`.

### Worked out on the desk

Pure functions in `frontend/src/ahead/` (`aheadGeometry.ts`, `aheadOdds.ts`, `macdFromPaths.ts`, `aheadScene.ts`),
memoised per symbol, minute and scope. Times are the chart's candle times.

**Lines to the meet** (Nova's arithmetic, no AI; shown whenever Ahead is on, in every scope and every AI state, with
or without a forecaster):

- From `read.level_map.lines.one_minute`, `state === "holding"` lines only; a broken line is never carried on.
  Support lines always rise and resistance lines always fall, so the outcome is `meet`, `none` or `past`. With
  several of a kind: the support with the highest price at or below the newest close, the resistance with the
  lowest at or above it.
- The anchor is the chart's newest completed candle, not the answer. Each line is re-anchored from its `now_t` by
  the number of chart candles in `(now_t, anchor]`: `p = now_p + slope * off` (`slope` is per candle).
- `past` (the lines are already past their meet) when resistance is at or below support at the anchor -- also when
  no support sits under the close or no resistance over it because the holding support has been carried above the
  holding resistance; `none`, with words, when either line is missing. Otherwise `kc = (pR - pS) / (sS - sR)` candles after the anchor and `p = pS + sS * kc`; `withinZone` when
  `kc <= 15`.
- The meet has a clock time only when the answer's `bars.contiguous_tail` is at least 30 (with no answer: the
  chart's own newest 30 candles are consecutive minutes); otherwise it is "in N candles". A meet's time and price
  are labelled "≈": the slopes and prices are rounded.

**Walls** (scope `all`):

- Candidates are `read.level_map.intraday` zones with at least one member whose kind is not `whole`, `half` or
  `vwap`: a level the candles built, not a round number or VWAP.
- Side is worked out again against the answer's `price` (the newest completed close): above when `lo > price` (the
  wall is `lo`), below when `hi < price` (the wall is `hi`); a zone holding the price is skipped. The nearest each
  side. With no AI view shown, the chart's newest close stands in for `price`. If the wall above is not above the wall below, there are no walls, with the reason.

**Which wall first** (only while the AI view is shown): for each path, the first minute whose close is `>=` the wall
above counts above, `<=` the wall below counts below, none counts neither; the shares are over `n` paths, by
`as_of + 15 min`. Beside the odds, always: the paths are the forecaster's minute ranges joined by an assumed path
shape (`paths.joined_by`), closes only (a wick is not seen), and "the nearer wall wins more often: that is distance,
not a call on direction".

**If it breaks** (under every wall, only while the AI view is shown; `AheadWalls.breaks`, an optional field, `null`
otherwise). On the same raw path closes:

- The wall above is a zone `[lo, hi]` over the price. A break is the first minute whose close is `> hi` (the zone's
  FAR edge, its top). From that minute on, the break minute included, the first of: a close `>=` the next wall above
  (the nearest wall zone wholly over `hi`, at its `lo`) is follow-through; a close `< lo` (back under the zone) fails;
  neither by `as_of + 15 min` is still open. A break and its follow-through in the same minute (a gap past both walls)
  counts as follow-through. With no next wall the race is holds (no close back under `lo`) against fails, and the words
  say there is no next wall within reach.
- The wall below is the mirror: a break is a close `< lo`; follow-through a close `<=` the next wall below's `hi`; a
  fail a close `> hi`.
- `AheadWallBreak = {share, nBreak, next, follow, fail, open}`: `share = nBreak / n`; `follow`, `fail` and `open` are
  over `nBreak`, `null` when no path breaks (`follow` also `null` with no next wall, when `open` is the holds share).
  `AheadWall` carries its zone's `lo` and `hi` beside `price` (the near edge).
- Every wall has one name, its price and its label ("4.56 · double bottom · VWAP"): the walls card's headline, its
  "if it breaks" line and the next wall it names all use it, and the chart chip carries the same price ("▼ 4.56
  first"); a wall is never written as its zone ("4.55–4.56").
- The walls card has one line under each wall ("If 4.69 · triple top breaks (38% of paths): 45% reach 5.00 · HOD
  first, 40% close back under 4.69, 15% still open (forecast)") with a smaller bar, and ends "A read of the
  forecaster's paths, not a signal: nothing here places an order." On the chart the wall's chip gains a short second
  line with a share before each word and never a share beside a price ("breaks 38% · then 45% reach 5.00 · 40% back
  under"; with no next wall "breaks 38% · then 50% hold · 40% back under") only when the zone is wide enough beside
  the full chip; it never leaves the zone, else the card alone carries it.

**If it triggers** (scopes `flat_top` and `first_pullback`):

- Lanes are `read.setups` rows whose `setup_type` is `flat_top_breakout` or `second_flat_top_breakout` (Flat top) or
  `first_pullback` (First pullback), long side, `timeframe` absent or `1m`.
- Rank: `armed` 3, `near` 2, forming 1 (`state` `leg` or `pullback` with a `forming` block). `triggered` gives the
  reason "Triggered at HH:MM: the plan card follows the trade" and no odds; `failed`, `filtered` and `watching` are not
  candidates. A tie goes to the trigger nearest the price.
- Levels: `armed` and `near` from the lane's `setup`; forming from its `forming` block, marked provisional. Trigger,
  entry, stop and first target are all needed, else a reason. A stock Nova does not follow (`read.followed` false)
  gives `read.followed_note`, or "Nova is not watching this stock's setups".
- On the raw path closes: the fill minute is the first `k` with close `> trigger` (none: not reached). From the fill
  minute on, the fill minute included, a close `>= target` is target first, `<= stop` stop first, else still open.
  `reach` is fills over `n`; the target / stop / open shares are over the fills (`null` with none). The words say
  "closes only; fills at the trigger". The drawn paths are coloured by their own outcome.

**The MACD fan** (only while the AI view is shown and the MACD pane is on): Nova's MACD (`computeMacdPane`) runs once
over the real closes up to `bar_t`; its EMA 12, EMA 26 and signal states at that point are carried through each
path's 15 closes with the same recurrences, and the MACD line's 10 / 25 / 50 / 75 / 90% are taken per minute. The
MACD is never forecast directly, and the pane says it is "MACD worked out from the AI's paths".

**Ghost volume** (only while the AI view is shown): per minute, an outline to the median of `ai.volume` and a whisker
from its 10% to its 90%. It never changes the volume scale: a top above the visible band is clipped and marked.

**What shows.** The AI view (fan, paths, odds, ghost volume, MACD fan) is drawn only when all hold: the state is
`ready`; `exam_passed` is true and `ai.exam.passed` agrees (else it is not a pass), or `unearned` is on; the scope is
not `lines`; and the chart's newest completed candle is `bar_t`. Otherwise none of it is drawn and the zone's
heading says why. The chips always say "AI view, not data";
shown before a pass, an amber "has not passed its exam" with the exam's numbers and scope; after a pass, "passed its
exam" with the scope and sample; a `null` scope reads "scope not stated"; with no exam, "no exam yet". The report
card's 80% line reads "should be near 80%".

**Every state has a sentence**, on the zone's heading and in the panel: each `ai.state`; the AI view hidden until
the exam is passed (with where to turn on "Show before it has earned it"); "Lines only: the AI view is off in this
scope."; "Ahead draws on the 1-minute chart." when no 1-minute pane shows; "No room at the right edge: the view is
yours -- scroll right or go to the live edge." (Ahead never moves a view the operator owns); "Reading the minute
that just closed…" and "Catching up to the chart…" (below); "This replay holds no 1-minute candles for {symbol}.";
and Nova's lines' own reasons (no holding line of a kind, the lines already past their meet). A fetch that fails
says so on the heading: a 404 is "Nova's API has no Ahead yet: restart the API after the update", no connection is
"Could not reach Nova's API", and a body that does not match this file becomes an `error` answer naming the field.

### Asking and drawing on the desk

- One poller per symbol, shared by every pane and tab, asking only for the visible tab with a 1-minute pane mounted
  and the switch on; nothing while the window is hidden.
- It asks about 1.5 s after the desk minute rolls over (the playhead's minute on a replay desk), so the candle has
  closed; while `pending`, every `retry_ms` (at most 15 tries); while `warming`, `offline`, `quiet`, `error` or
  `not_set_up`, every 15 s; once `ready` for the current minute, not again until the next.
- **Never over a real candle.** The AI view is drawn only when the chart's newest completed candle time equals
  `bar_t` (the forming candle may be at `bar_t + 60`). A newer completed candle on the chart: "Reading the minute
  that just closed…", no fan. A chart behind the answer: "Catching up to the chart…", no fan. A previous minute's
  forecast is never kept on screen.
- The zone starts half a candle right of `bar_t`'s candle; minute `k` (1-15) sits at the time scale's logical index
  of `bar_t` plus `k` (a fractional step, such as the lines' meet, between its two whole neighbours). Nothing is
  added to any series and the chart's right offset is never changed. The zone runs its full 15 steps in the price,
  volume and MACD panes alike, with the same left and right edges.
- **Framing.** When the switch comes on, and again on each new answer, a 1-minute view that still follows the live
  edge and that the operator has not zoomed or panned is framed like the approved mockup: the last 45 candles, the
  15-step zone and a 2-candle margin, plus the width of the stock read's word column right of the zone -- the zone
  takes about a quarter of the pane. When the pane's width changes (the Ahead panel docking beside the charts, or
  closing) such a view is framed again on the new width. A view the operator owns is never moved.
- **No word over a real candle.** Every chip stays inside the zone. When the zone is too narrow for a chip's words
  it shows the odds only ("▲ 42%", "neither 3%", "target 41%", "stop 6%"); narrower still, none (the panel has the
  words). A setup target within half a cent of a wall reads "target {price} · next wall". "lines meet ≈ HH:MM"
  sits over its ring and over the lines running into it; an odds chip that would sit on one of Nova's lines moves
  off it. The chips tied to a price (each wall's, a strategy's) are placed first, on their price; "neither in 15 min"
  (tied to no one price) is placed last, in the free space between the walls nearest their middle, and is left to
  the panel when there is none -- it never pushes a wall's chip off its wall. The minute labels (every 5 minutes) are on the time axis under the zone, in the axis's own words
  ("9:05 AM"); "AI volume" sits on a chip just over the ghost bars under it. The zone ends just past the last ghost
  bar, in every pane.
- **The legend** ("Nova's lines carried on until they meet", "likely range: inner half, outer 80%", "16 of {n}
  possible paths", "AI volume", "hatched = drawn, never recorded", each with a swatch) is in the Ahead panel's first
  card, never laid over the candles or the volume. Its AI rows show only while the AI view is drawn. While Ahead
  draws on a pane, the same marks with the same swatches are the first section of that pane's Key ("Ahead (AI view, not
  data)"; `stock_read/paneKeyExtras.ts`), one label each with words that do not repeat it, plus the meet ring (while
  the meet is in the zone), the wall chips ("▲ / ▼ first": the share of paths reaching that wall first) and the break
  line (while a wall chip carries one), so the zone reads with the panel closed. The Key's card fits its pane: it is
  measured as it opens and scrolls inside the height the pane leaves under its chip.
- **Prices stay in the price area.** The fan and the drawn paths are clipped at the top of the volume band (the
  volume overlay's top scale margin) so they never run over the real or ghost volume bars; a path that leaves the
  price area there, or over the pane's top, gets a small caret at that edge. The hatch runs the pane's full height.
- The heading ("AHEAD · next 15 min", its tags and sentences) and "now HH:MM" just left of the zone are DOM over the
  pane on a backdrop of the desk's panel colour at 0.9, so a level line drawn across the pane's top passes behind
  them.
- **The panel never covers the 1-minute pane.** That pane publishes its own span and its zone's (to the pane's
  right edge, price axis included). With room beside the pane for the panel (at least 300 px; the desk's 2x2 grid,
  the 1-minute pane its bottom-right one) the panel slides over the other panes on the roomier side, below the chart
  grid's toolbar, as wide as that room allows (at most 520 px or 62% of the grid). With no such room (the pane fills
  the grid, or is maximised) the panel docks on the side away from the zone (at most 520 px or 34% of the grid, at
  least 300 px) and the chart grid gives up that width while it is open: toolbar, candles, zone, chips and price
  axis all stay in view, and the pane is framed again on its new width. The panel ends at its holder's bottom or the
  window's, whichever is higher, and its cards scroll inside it, so the last card is always reachable. Every card
  that shows AI numbers carries "AI view, not data" and the exam's status in the chart chip's words ("no exam yet",
  "has not passed its exam" in amber, "passed its exam" in green). The report card has one row per score -- price
  inside its 80% range (should be 80%), volume ranking and range ranking (1 = perfect, 0 = no better than chance) --
  each "—" until scored, never a zero; with nothing scored it adds "Not scored yet: scoring starts when the
  forecaster answers."

### On a Sim replay

The desk clock is the playhead. The backend sends only bars that ended at or before it (a bar that ends after
the playhead fails closed to `error`, never sent), so `generated_at >= as_of` on every answer. On a scrub
(`nova:sim-clock-scrub`) the desk drops the symbol's answer and asks again at once; after a rewind it drops any
answer whose `generated_at` is more than 2 s after the playhead. Requests from a replay are sent with `venue: "sim"`
and are never counted in the forecaster's live score. At the live edge the Sim desk reads the live feed, as Paper
does.

### The demo build

The public demo has no forecaster. It answers `not_set_up` with "This demo has no forecaster: Ahead shows only Nova's
own lines here" and a status with `configured: false` (Nova Marketing Sample Data; `sampleAhead.ts`). It never draws
a forecast.
