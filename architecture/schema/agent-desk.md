# Data schema: Agent desk and the day movers index

## Optional historical chart MCP adapter (2026-10-18)

`tools/nova_chart_mcp.py` is an optional external stdio adapter using the official
Python MCP SDK, pinned separately in `tools/requirements-chart-mcp.txt`. The SDK
owns protocol parsing, discovery and transport. No MCP listener is added to the
trading application. Missing SDK fails before starting transport; nothing installs
dependencies or edits client configuration automatically.

The tool `nova_historical_chart(symbol, date, output_name, samples=0, as_of_m=None, annotations=None)`
requests one exact historical symbol/day, with optional causal minute cutoff `as_of_m`
(`0..1440`) and optional `0..32` `annotations` (`horizontal_line` / `time_marker`).
The companion tool `nova_historical_chart_gallery(entries, output_name, family="historical-chart", samples=0)`
exports `1..9` symbol/day entries in a single pass and returns the verified 3x3 overview
PNG inline alongside all detail image manifests. `symbol` is an ASCII resolver token,
`date` is a valid ISO calendar date, `output_name` is a single new child directory name,
and `samples` is a strict integer 0..50. Tool inputs supply no root, command, URL or
environment variable. Trusted launch arguments supply the resolver and gateway
checkouts, local minute root, optional `--fallback-massive-root`, existing dedicated
output root and optional export Python executable. The adapter validates compatible
official MCP SDK `1.x` (`>=1.26.0`, `<2.0.0`). Local roots reject network drives, traversal and every reparse
component; the explicit Windows App Execution Alias exception applies only to the
trusted executable token, never data/output roots.
When no export interpreter is supplied, non-Windows launchers canonicalize the
already-running SDK interpreter before validating it. Explicit interpreter paths
retain strict symlink/reparse rejection; Windows execution-alias handling is unchanged.

The adapter launches only `tools/nova_historical_charts.py export` from the trusted
resolver checkout, forwarding trusted roots. The resolver owns local schema and
coverage validation and delegates to the native renderer. One request runs at a
time within 240 seconds, with the gateway's owned-process helper. Timeout,
cancellation or unverified cleanup cannot return success. Logs never enter MCP
stdout and errors use fixed codes. No live history, desk/Sim command, broker call,
automatic retry or second renderer is exposed.

Success returns bounded structured PNG paths/SHA256 and receipt identity confined
to the new output directory, with zero active owned processes verified. The SDK
result also includes exactly one inline PNG: the unique verified paired 1m/5m
detail artifact. Before encoding, re-read at most 2MiB plus one byte and recheck its
PNG signature and manifest hash. Missing/ambiguous, oversized or changed inline
artifacts return a fixed error with no image; verified export metadata is retained
for local diagnosis. This adds no arbitrary image/file reader or resource endpoint.
Original
input paths/provenance stay in local receipts, not the MCP response. Failed output
is preserved. There is no arbitrary file/resource reader, persistent host
registration or permission grant. Each client and its exact roots/capability need
explicit operator approval. See [NOVA_CHART_MCP.md](../../docs/NOVA_CHART_MCP.md).

## Historical OHLCV chart gateway (operator, 2026-10-18)

Agents export historical OHLCV through Nova's existing candle, volume and snapshot
renderer. The gateway accepts immutable local inputs and generic annotations; it
does not discover instruments, obtain market data, evaluate strategies or execute trades.
The command and receipt contract are in [NOVA_CHART_EXPORT.md](../../docs/NOVA_CHART_EXPORT.md).

### Frozen selection and projections

Selection:
{schema_version:1, kind:"historical_ohlcv", family, selected:[{day,ticker,as_of_m?,annotations,bar_projection:{path,sha256}}]}.

- family is a caller-supplied label. selected contains 1..9 entries, unique by
  (day,ticker,as_of_m) and ordered by that identity; a ticker may appear on different
  dates or with different as-of boundaries.
- day is an ISO calendar date; ticker is an exact nonempty identifier.
- as_of_m is optional: an integer 0..1440, never a boolean, denoting an ET minute
  boundary. Omit it to view the full observed session without a future-context mask.
- annotations is a required array of 0..32 allowlisted objects. Unknown kinds or
  fields fail validation. Labels are nonempty text of 1..80 characters. Optional
  color is one of blue, gold, grey, green, red; omitted means blue.
  Colors map to fixed renderer values, never arbitrary CSS.
  - {kind:"horizontal_line",price,label,color?}: finite positive price.
  - {kind:"time_marker",minute,label,color?}: integer minute 0..1439, not boolean.
  - {kind:"trade_marker",side,second,price,label,color?}: a caller's fill. side is
    buy or sell; second is the finite ET second of the day 0<=second<86400 (fractions
    allowed); price is finite positive. Drawn with the desk's fill arrows
    (`FillMarkersPrimitive`) on the bar holding that second: a buy arrow under the bar,
    a sell arrow over it; default color green for buy, red for sell. Never inferred.
- bar_seconds is optional: 1, 5, 10, 15 or 30, and never with as_of_m. When present
  the projection is a sub-minute projection (below) and the entry renders one
  `<n>Sec` pane instead of 1Min + 5Min.
- bar_projection.path is an explicit absolute path under the selection's sibling
  bars/ directory. Its SHA256 binds the exact file bytes. Paths are not accepted
  from HTTP requests.

Each projection contains
{day,ticker,time_zone:"America/New_York",m_semantics:"minute_START",price_units:"raw_same_session_YYYY-MM-DD",observed_source_start_m,observed_source_end_exclusive_m,bars:[{m,o,h,l,c,v}]}.
Identity and units must match the selection entry. Bounds are integer minute starts
with 0<=start<end<=1440; bars are ordered, unique, inside those bounds, and use
finite coherent positive OHLC and finite nonnegative volume. No interpolation,
unit conversion or synthetic flat candles occurs. Invalid visible-prefix data
fails closed; with an as-of boundary, later unavailable OHLCV remains a gap.
Malformed timestamps or duplicate minutes fail validation.

A sub-minute projection (entry has bar_seconds) contains
{day,ticker,time_zone:"America/New_York",s_semantics:"second_START",bar_seconds,price_units:"raw_same_session_YYYY-MM-DD",observed_source_start_s,observed_source_end_exclusive_s,bars:[{s,o,h,l,c,v}]}.
bar_seconds matches the entry; bounds are integer ET seconds with 0<=start<end<=86400;
each s is on the bar_seconds grid, ordered, unique and inside the bounds; every row
has coherent positive OHLC and nonnegative volume (a bucket with no price-setting
print is absent, never a flat candle). No 5m aggregation is formed for these entries.

Only five actual consecutive observed minute starts form a wall-clock 5m candle.
Without as_of_m, the complete observed session is displayed. With it, candles
starting at/after the boundary and 5m candles crossing it are shaded amber in their
whole displayed width. A missing boundary bucket never moves the shading beyond
later candles. The view and exported PNGs share this boundary calculation.

### Read-only wire and rendering

GET /api/agent/chart-gallery returns
{schema_version:1,kind:"historical_ohlcv",selection_sha256,family,entries:[{id,symbol,date,as_of_m?,as_of_t?,annotations,bars_1m,bars_5m,bar_seconds?,bars_sub?,source}],timings:{load_ms,aggregation_ms}}.
Bars use Nova's {t,o,h,l,c,v} UTC-ISO shape. A sub-minute entry carries bar_seconds,
a nonempty bars_sub and empty bars_1m / bars_5m; a minute entry carries neither. as_of_t, when present, is the same
boundary as as_of_m expressed as a UTC timestamp. The response is immutable and
hash-bound; no request writes source files. source contains only the allowlisted
selection_sha256 and projection_sha256 hashes; arbitrary provenance is not returned.

frontend/chart-gateway.html reuses Nova's chart instance, bar conversion, paint and
native canvas snapshot. The page mounts no trading app, order context, live cache,
market-data subscriptions or simulation commands. Only the bounded annotations above
are rendered. Selection validation is presentation validation, not a trading signal.

### Export lifecycle

tools/nova_charts.py export --selection FILE --sha256 HASH --output NEWDIR validates
frozen inputs, starts isolated data/renderer/browser children on available loopback
ports, exports PNGs and writes EXPORT_RECEIPT.json. Existing output directories are
refused. The receipt reports image paths/hashes, phase timings and cleanup status;
logs and partial output remain available after failure. Detail PNGs are named
`NN_<TICKER>_<date>_1m_5m.png`, or `NN_<TICKER>_<date>_<n>s.png` for sub-minute entries.

The renderer is a production build of the chart-only page served by `vite preview`
(a dev server spent about 9 s of every export compiling modules on first load).
`tools/nova_chart_runner.py` owns the build under `frontend/.chart-gateway-build/<key>/`
(git-ignored; no schema, a build artifact): `key` hashes every `frontend/src` file's
path, size and modification time plus the gateway page, its Vite config and the
lockfile, so any edit rebuilds once (into a temp folder, then moved) and drops older
builds. The receipt reports `renderer_bundle` and `renderer_bundle_ms`.

On Windows, each command starts suspended, joins an owned unnamed Job, and only then
runs, so it and everything it starts are in the Job before it executes (#1061: under
Microsoft Store Python a program from outside the package, such as `node`, started by a
packaged process is created outside the creator's Jobs, so inheritance alone leaked
every renderer). Cleanup ends the Job, verifies zero active Job processes, and also
walks each command's live descendants by parent PID and creation time (taken before
the Job ends, so a reused PID never matches): a descendant still alive outside the Job
is stopped. The receipt reports `active_owned_processes`,
`live_descendants_after_cleanup` (must be 0 for `ok`) and `escaped_job_descendants`
(how many had to be stopped outside the Job; expected 0).
A random per-run instance token proves each service's identity. Readiness ignores
inherited proxies, rejects redirects and never adopts an unrelated port listener.
The chart-only Vite configuration loads no environment files. Other operating systems
must have an equivalent tested ownership boundary before service launch is supported.
The command imports no trading-app lifespan and leaves the running desk intact.

#### Warm renderer (opt-in, #1062)

`tools/nova_chart_warm.py` owns one long-lived renderer per gateway checkout, so a
caller that asks for it (`--warm`) skips starting and stopping the isolated children
each export. Owner: its `serve` process, started by `start` or by the first `--warm`
export, and ended by `stop`, by its idle timeout (`--idle-seconds`, default 600,
1..3600, counted from the last job), or by its renderer or driver exiting. It owns, in
one Job as above, `vite preview` of the current renderer build and one Node driver
(`tools/nova_chart_export.mjs --serve`) holding a headless Chromium; if the owner dies
abruptly the Job's kill-on-close ends both. Shutdown closes the Job and logs the
verified count to `frontend/.chart-gateway-build/.warm-service.log`.

- Rendezvous `frontend/.chart-gateway-build/.warm-service.json`
  `{schema_version:1, pid, pipe, authkey, bundle, renderer_base, instance, idle_seconds,
  started_utc}`: written by the owner once ready, removed on shutdown; an unknown
  `schema_version` is refused, and a file whose pipe does not answer the authkey is a
  stopped service (removed). Callers talk over that local named pipe with
  `multiprocessing.connection` authentication (HMAC challenge on the 32-byte key) and
  JSON bytes, never pickle. One job at a time.
- A job is `{op:"export", selection, sha256, output, samples}`, exactly the one-shot
  export's inputs. The owner checks them the same way (new output, `load_gallery` hash
  and shape), then the driver opens a fresh browser context whose only allowed origin is
  the renderer, and answers the page's single `GET /api/agent/chart-gallery` in the
  browser with the validated body (no data port is opened; paths are never taken from
  HTTP). After capture the frozen bytes are verified again, and the renderer sources
  are re-hashed: a build that no longer matches the sources fails the job as `stale`
  and ends the service, so a warm export never draws with an old renderer.
- Its `EXPORT_RECEIPT.json` has the one-shot fields for the export (selection hash,
  images and hashes, capture verification, `source_data_mutated:false`,
  `broker_or_desk_calls:false`, `cleanup_errors`) plus `renderer:"warm"` and
  `warm_service:{pid, owned_pids, live_owned_processes, jobs_served, idle_seconds}`. It
  has no `owned_trees_stopped`: the renderer is meant to stay up, and the receipt says
  which process owns it instead of claiming it stopped. One-shot receipts carry
  `renderer:"cold"`. The MCP server's verification accepts only one-shot receipts.

The generic local historical resolver accepts one explicit minute-Parquet root,
symbol and date; see [local-historical-charts.md](local-historical-charts.md).
It produces this same frozen selection and delegates to the renderer above. The trade
front door (`tools/nova_trade_charts.py`, MCP `nova_trade_charts`) turns a trade list
into sub-minute entries with trade markers; see "Trade charts" in
[local-historical-charts.md](local-historical-charts.md).
There is no discovery, download or simulation fallback. Optional MCP tooling uses
this generic chart interface; client installation/configuration and per-action grants
remain explicit and separate.

### Timing

The subsecond target concerns initialized rendering with data already available.
Report source loading, aggregation, first/warm fetch and paint, native capture/PNG
composition, process startup and file transport separately, with sample counts and
p50/p95 when benchmarked. The default --samples 0 avoids repeated captures.
Never claim a subsecond complete command without measuring its full path.

Part of `AGENTS.md` §3 (Data Schema), which indexes every file in this folder. Owners: backend/agent_desk/, backend/day_movers/, research/movers/. Same law as the constitution: a wire or persisted shape changes here first, in the same commit as the code (Invariants #1 and #5).

## Agents find stock-days and show them in the Sim (ADR 050, operator ask 2026-10-06)

"Go to a small-cap stock that increased, where the high of the day was 300% ... punch it in on the simulator so I
could see it", then "this is just going to be for agents for now ... like some secret endpoints that they can
manipulate and show me." Owners `backend/day_movers/` (the index), `backend/agent_desk/` (the routes, commands,
dictionary), `research/movers/` (the builder), `frontend/src/agent_desk/` (the desk side), `tools/nova_agent.py`
and `.claude/skills/nova-sim-navigator/`. Nothing here places, stages or cancels an order, or arms the desk.

- **The index.** `<NOVA_MARKET_DATA_DIR>/movers/day_movers.sqlite3` (`PRAGMA user_version = 1`; an unknown
  version refuses), written only by `research/movers/` through `day_movers.store`:
  - `sessions (session_date PK, prev_date, tickers, rows, minute_bars, builder, built_ts, note)` -- one per
    session built: `tickers` the day bars that session, `minute_bars` 1 when the minute file was read.
  - `movers`, primary key (session_date, symbol): `kind, prev_date, prev_close, prev_volume, split_factor,
    split_listed, split_suspect, open, high, low, close, volume, pm_high, pm_low, pm_volume, ah_high, ah_low,
    ah_volume, day_high, day_high_ts, day_low, day_low_ts, dollar_volume, first_ts, last_ts, high_pct, low_pct,
    close_pct, gap_pct, up10_ts, up20_ts, up50_ts, up100_ts, up300_ts, down10_ts, down20_ts, down50_ts`.
    - `kind`: the Massive reference type (`CS`, `ADRC`, `WARRANT`, ...; null when the reference has none).
    - `prev_close`: the official close of `prev_date`, the session before in the files, times `split_factor` for
      a split Massive lists or `confirm_splits.py` proved executing in between (`split_listed` 1); null when the
      stock did not trade that session, never an older close. `prev_volume` is that session's volume on today's
      share basis.
    - `open` / `high` / `low` / `close`: the day bar's official prices -- regular hours (no extended-hours Form T
      print sets them; the closing cross does), the official close. `volume`: the day bar's, the whole session
      04:00-20:00 with odd lots, so `pm_volume` and `ah_volume` are inside it.
    - `pm_*` 04:00-09:30 ET, `ah_*` 16:00-20:00 and `day_high` / `day_low` 04:00-20:00 come from the minute bars,
      with the start of the first minute that printed each (`*_ts`, epoch seconds; null when the day bar's own
      high or low is beyond every minute, as a thin name's closing cross or a late-reported `Z` trade can be); `dollar_volume` is the minutes'
      close x volume, which leaves out the closing cross (the minute bars carry none); `first_ts` / `last_ts` the
      first and last minute that printed.
    - `*_pct` are fractions against `prev_close` (`gap_pct` from the 09:30 open; null without a prior close);
      `upN_ts` / `downN_ts` the first minute whose high reached +N% (whose low reached -N%); a price exactly on
      the line reaches it (`DAY_MOVERS_LINE_EPS`).
    - `split_suspect` 1 when the open is 1.8x or more (0.7x or less) the prior close and no split is listed.
    - A row is kept when the high is +10% or the low -10%, the close or the gap is 5% either way, or a split
      suspect; without a prior close, when the day's high is 20% over its low.
  - `sec_shares (symbol, cik, as_of, filed, shares, form)`: shares outstanding a filing reported as of `as_of`,
    from SEC's companyfacts (`research/movers/export_sec_shares.py`; several share classes keep the largest).
  - `splits (symbol, execution_date, split_from, split_to)`: the split list the builder adjusted prices by.
- **Routes** (`/api/agent`, loopback clients only; every write needs `X-Nova-Api-Key` even on loopback;
  percentages on this wire are percent points):
  - `GET /api/agent` -> `{schema_version: 1, endpoints: [{method, path, does}], index: {ok, error, path,
    sessions, first, last, files_last, behind, missing, rows}, dictionary: {entries, error}, desk: {listening,
    last_poll_ts, window_id}, rules: string[]}` (`behind`: minute-file days newer than the newest session built;
    `missing`: minute-file days not built; both null when the folder cannot be listed).
  - `GET /api/agent/movers` -> `{schema_version: 1, query, units: "percent", count, rows[], summary, excluded,
    coverage, notes[]}`. Query: `from`, `to`, `symbol`, `kinds` (default `common`: `CS`, `ADRC`, and a ticker of
    1-4 letters the reference has no type for), `price_min` / `price_max` (the prior close), `high_min` /
    `high_max`, `low_min` / `low_max`, `close_min` / `close_max`, `gap_min` / `gap_max` (percent; a stock exactly on
    the limit passes it), `close_pos_min`
    / `close_pos_max` (0 = closed at the day's low, 1 = at its high), `giveback_min` / `giveback_max` (the share
    of the run over the prior close given back by the close, 0-1), `high_after` / `high_before` (`HH:MM` ET),
    `volume_min`, `dollar_volume_min`, `float_max` (shares), `float_unknown` (`exclude` | `include` | `only`),
    `replayable` (only days whose trades file is on disk), `splits` (`exclude_likely` default | `include` |
    `only_suspects`), `sort` (`newest` | `oldest` | `high` | `low` | `close` | `gap` | `volume` |
    `dollar_volume`), `limit` (default 25, at most 500). A row is `{date, symbol, kind, prev_close, open, high,
    low, close, volume, dollar_volume, day_high, day_high_et, day_low, day_low_et, pm_high, ah_high, high_pct,
    low_pct, close_pct, gap_pct, close_pos, giveback, first_et: {up10, up20, up50, up100, up300, down10, down20,
    down50}, replayable, split: null | "listed" | "suspect" | "likely_split", float: {shares, source:
    "recorded" | "enrichment" | "sec_shares_outstanding" | null, as_of, proof: "pass" | "fail" | "unknown"} |
    null}` (`float` only when `float_max` is asked). A split suspect is a `likely_split` when it traded no more
    shares than `prev_volume`, and no split at all (`null`, a real overnight move) when it traded 3x or more
    (#772). `summary` covers every match, not only the rows returned: `{matched,
    closed_above_prior_close, closed_above_open, closed_top_third, closed_bottom_third, median_high_pct,
    median_close_pct, median_giveback}` (shares of `matched`, in percent). A search matching more than
    `AGENT_MOVERS_MAX_SCAN` stock-days answers `too_broad: true` with the count only. `GET
    /api/agent/movers/{date}/{symbol}` -> `{schema_version, row, coverage}` (`AGENT_NOT_IN_INDEX` 404).
    Refusals: `AGENT_INVALID` 400 with `field`, `AGENT_INDEX_UNAVAILABLE` 503 (not built, or unreadable).
  - `POST /api/agent/show {symbol, date, at?: "run" | "drop" | "high" | "low" | "open" | "premarket" | "HH:MM",
    confirm?: boolean}` -> 202 `{command}`. A run or a drop parks five minutes before its first +20% (else +10%)
    mark; a mark the stock already stood at within five minutes of its first print is where it opened, so the
    next mark it reached later (+50%, +100%, +300%) is taken, else the day's high (low). The window loaded is
    135 minutes from the quarter hour 30 minutes before the park (so the charts show what came before), with 60-
    and 30-minute windows to fall back on when the Sim's print or quote cap refuses it. Refusals are `{detail: {reason, error, ...}}`: `AGENT_INVALID` 400 (also a day not over yet),
    `AGENT_NOT_ON_FILE` 404 (no trades file for that day), `AGENT_NO_DESK` 409 (no main desk window listening),
    `AGENT_AT_STAKE` 409 with `at_stake: {venue, safe, items: [{kind, venue, symbol, text}], unknown: [{kind,
    error}]}`. A new show replaces one not finished (`cancelled`).
  - `POST /api/agent/move {to?: "high" | "low" | "run" | "drop" | "open" | "premarket" | "HH:MM", by_min?: number,
    paused?: boolean, confirm?: boolean}` -> 202 `{command}`; `AGENT_NOTHING_LOADED` 409 unless the Sim holds a
    window. A target outside the loaded window loads one around it (`AGENT_AT_STAKE` as a show's).
  - `GET /api/agent/commands/{id}?wait=` -> `{command}`, waiting up to `wait` seconds (at most 30) for a change;
    `GET /api/agent/commands` the newest; `POST /api/agent/commands/{id}/cancel`. A **command** is `{id, kind:
    "show" | "move", status: "queued" | "running" | "done" | "failed" | "expired" | "cancelled", created_ts,
    updated_ts, args, plan, step, steps: [{step, ts, text}], result, error, claimed_by}`. A show's `plan` is
    `{symbol, date, at, anchor_et, park_et, park_ts, park_words, window, fallback_windows, switch_venue,
    in_index}` and a move's `{symbol, date, paused, target_ts, target_et, target_words, loaded_start_ts, window,
    fallback_windows}` (`park_words` / `target_words`: where it lands, in words), a window `{start, end, start_ts,
    end_ts}` (ET `HH:MM` and epoch seconds). A command no desk window takes within `AGENT_COMMAND_CLAIM_SEC`
    (15 s) expires. One a window took and never reported on within `AGENT_COMMAND_FIRST_REPORT_SEC` (10 s) goes
    back in the queue -- a reloaded or closed window's poll can still be waiting on the server -- at most three
    times, and the desk's poll gives a command back at once when its request is gone; one the desk stops
    reporting on for `AGENT_COMMAND_LEASE_SEC` (90 s), or still running after `AGENT_COMMAND_STALE_SEC`, fails.
  - `GET /api/agent/desk` -> `{schema_version: 1, venue, live_edge, sim: {session_date, playhead_et, paused,
    loaded: {source, symbol, date, start, end} | null} | null, focus: {page, symbol, window_id} | null,
    listening, at_stake}`.
  - `GET /api/agent/dictionary` -> `{schema_version: 1, error, entries[]}`; `POST /api/agent/dictionary {entry}`
    adds or replaces an operator entry by `id`; `DELETE /api/agent/dictionary/{id}`.
  - The desk's side (keyed, the long poll too): `GET /api/agent/desk/next?wait=&window_id=` (the main window's
    long poll, `{command | null}`, the command now `running` and its) and `POST /api/agent/desk/commands/{id}
    {status: "running" | "done" | "failed", step, text, result?, error?}` -> `{command}` (a command already
    cancelled or expired answers as it is, and the desk stops).
- **The dictionary** (operator: "If I'm obviously asking for a command ... I want it to be added to our
  dictionary"): `<cache_dir>/agent-dictionary.json` = `{schema_version: 1, entries: [{id, phrases: string[],
  means, call: {method, path, params?, body?}, then?, notes?, added_by, added_at, updated_at}]}`, written through
  a temp file and a rename. Seed entries live in code (`seed: true` on the wire); an operator entry with a seed's
  id replaces it. An unknown version or an unreadable file reads as the seeds with the error stated, and writes
  are refused `AGENT_DICTIONARY_UNREADABLE`. Nova defines no shape words: an agent turns words into the numbers
  above, asks when they have no agreed meaning, and saves what the operator confirms.
- **At stake** (operator: switch "when nothing is at stake"; owner `agent_desk/safety.py`): on the venue the
  desk would leave, a position or a working order (Paper's ledger, Live's IBKR cache), the Bot on, an open bot
  or Nova trade, a Nova stock mode or approval, or the desk armed; and, when the show or move loads another Sim
  window (which starts the Sim's scratch account over), the Sim account's positions and working orders. A check
  that cannot be read is at stake too. `confirm` is sent only after the operator agreed in the chat.
- **The desk side.** Only the main window (never a Trader pop-out, the sample desk or the demo) long-polls for
  commands. It runs them with the desk's own steps -- venue, Sim day, Trader tab, the Massive window, the wait
  for its import, the playhead (paused) -- reports each step, and shows a notice of what it is doing. A window
  refused for the print or quote cap is retried with the plan's narrower windows.
- **Float** (operator: proven, else unknown; owner `day_movers/floats.py`): `float_max` passes on the float
  Nova knew that day (the desk's enrichment snapshot in `archive.db`, 2026-07-28 on) at or under the limit, or
  on `sec_shares` at or under the limit -- a float cannot exceed the shares outstanding: the newest count filed
  by the session, as of a day on or before it and at most `DAY_MOVERS_SEC_SHARES_MAX_AGE_DAYS` (120) before it,
  put on the session's basis through the splits listed in between. Shares issued after the count are not in
  it, and the answer carries its `as_of`, `filed` and `age_days`. A snapshot over the limit fails; anything
  else is unknown, never today's float.

## The data front door over MCP (ADR 059, operator 2026-10-18)

Operator: "a standard way MCP to allow agents to access data in standarized form with endpoints so agents are able
to find the correct data." One library (`research/market_reads`), its command line (`tools/market_data.py`) and its
MCP server (`tools/nova_data_mcp.py`, official SDK, stdio; registered in `.cursor/mcp.json` and `.mcp.json` as
`nova-data`). Read-only on the data; the catalog, prose and traps are `docs/market-data.md`.

- **Tools** (each answers a JSON object; a failed read is `{ok: false, error: "<Type>: <message>"}`, never a crash):
  `data_catalog` (`{ok, datasets: [{name, source, history, as_of, units, mcp, cli}], not_here: string[]}` -- call it
  first), `data_status`, `stock_day {kind: trades|quotes|bars, symbol, day, start?, end?, tf?, adjust?,
  output_name?}`, `movers_search {params}` (the `/api/agent/movers` answer, at most 500 rows), `movers_scan {filters,
  symbol?, kinds?, columns?, limit?, splits?, output_name?}`, `board {day, at, list_name, source?}`, `splits {symbol,
  day?, cik?}` (`price_factor` with `day`), `financials {symbol, statement, as_of?, timeframe?, cik?}`, `sec_shares
  {symbol, day?, max_age_days?, cik?}`, `sec_filings {symbol, as_of?, forms?, cik?}`, `float_latest {symbol?}`, `ipos
  {symbol?, date_from?, date_to?}`, `ticker_details {symbol}`, `short_interest {symbol, day, at?}`.
- **`stock_day` bars** take `tf` as a count and `s` / `m` / `h`; a daily `tf` (`1d`, `1w`) is refused naming the
  daily bars tool. Minute bars carry Massive's own volume; seconds bars sum every trade except cancel / error
  records (`docs/market-data.md`, "Two volume rules").
- **`movers_scan`** applies the capped search's split rule (`day_movers.query.splits_sql`: `splits` =
  `exclude_likely` default | `include` | `only_suspects`) and its percent-line tolerance (`query.pct_bound`); a row
  selecting `split_listed, split_suspect, prev_volume, volume` (every column does) gains `split` (`listed` |
  `likely_split` | `suspect` | null). It refuses a call without `date_from` / `date_to`, a symbol or a `limit`; a
  `limit` is 1-1,000,000; without one at most 100,000 rows return and `meta.capped` (bool) / `meta.note` say more
  matched. `meta.filters.splits` echoes the choice.
- **`board`** answers `change_pct` / `gap_pct` in percent points (the store keeps fractions) and adds top-level
  `covered` (false when the day has no board, recorded or rebuilt), `gap` (`{start, end, reason, stop}` or null)
  and `note` when not covered.
- **A ticker two companies used** (`research/market_reads/tickers.py`, over `reference/tickers.json`): SEC shares /
  facts / filings, financials and splits read the company that held the ticker on the asked day (former holder
  until its `delisted_utc` day; today's holder from its ticker-details `list_date`, else the day after the former
  left; overlaps settled by whose SEC filings span the day, then by the only `CS` / `ADRC` candidate, with the
  warning kept). Answers carry `ticker {cik, name, ticker_reused, rule,
  warning, candidates: [{cik, name, held_from, held_to}]}` (`meta.ticker` on tables). A day that cannot be settled
  is `{ok: false, error: "LookupError: ... could be A or B: pass cik="}`; `cik` reads one company. Without a day
  the read is today's holder with `warning` naming the others. `splits` without `day` adds `holder_cik` per row
  for a reused ticker; financials keep only statements whose own `cik` is the holder's.
- **A table answer** is `{ok: true, meta, rows, columns, data, truncated, out}`: `rows` matched, `data` the first 200
  as records, `meta` the read's attributes (its as-of rule, units, source). `output_name` (a new plain
  `*.parquet` / `*.csv` name) writes every row under `--output-root` (default `<temp>/nova-data-mcp`) and `out` names
  it; an existing name or a path is refused. Only `stock_day` and `movers_scan` write (`readOnlyHint: false`,
  `destructiveHint: false`); every other tool is `readOnlyHint: true`.
- **`sec_shares` with `day`** is `{symbol, day, cik, entity, rule, outstanding, issued, treasury, public_float_usd,
  filer}`; each value `{value, concept, end, filed, form, age_days}` or null -- the newest fact filed on or before
  `day` whose period `end` is on or before it. `outstanding` is the cover page's `EntityCommonStockSharesOutstanding`,
  else the balance sheet's `CommonStockSharesOutstanding`, times `split_factor` (splits executed after `end` through
  `day`); `max_age_days` nulls an older one. `public_float_usd` is the 10-K's `EntityPublicFloat` (dollars). `filer`
  is `domestic` (newest annual report filed by `day` a 10-K), `foreign` (20-F / 40-F) or `unknown`.
- **Units and as-of.** Movers percents are points in and out (the store keeps fractions). Financial statements count
  from `filing_date`; SEC facts and filings from `filed`; FINRA short interest from `move_reason.short_interest`'s
  publish lag. `float_latest` and `ticker_details` say `as_of: "latest_only"`: never a past day's.
- **Reference index** (owner `research/market_reads/reference.py`): `<NOVA_MARKET_DATA_DIR>/store/
  reference_index.sqlite3`, `PRAGMA user_version = 1` (another version refuses `UnknownIndexVersion`). `sources
  (dataset, file, size, mtime_ns)` and `rows (dataset, ticker, cik, day, data)` -- `data` the dump's record as JSON,
  one row per ticker a statement names, `day` the dataset's date (`filing_date`, `listing_date`, `effective_date`).
  A dataset is rebuilt in one transaction when any source file's size or time differs from `sources`.
- **Heavy-read slots** (`research/market_reads/slots.py`): bulk scans, index builds and `stock_day` take one of
  `NOVA_MARKET_READ_SLOTS` (default 2) OS-locked files in `<temp>/nova-market-read-slots`; a slot dies with its
  process; waiting past 600 s raises `Busy`.
- **Read cache** (owner `research/market_reads/read_cache.py`): `reads.read_file` (so `trades`, `quotes` and
  minute `bars`) keeps each stock-day it parses in `<root>/<dataset>/<YYYY-MM-DD>/t_<SYMBOL>.arrow` (Arrow IPC, zstd;
  `t_` so a ticker such as `CON` never names a Windows device, any byte outside `A-Z 0-9 . _ -` written `%XX`): the
  symbol's whole day as parsed, before the window and `time_et`. The schema's metadata key `nova_read_cache` holds
  `{schema_version: 1, dataset, symbol, day, source: {path, size, mtime_ns}, reader, indexed, header, rows}`;
  `reader` is a hash of the code that finds and parses the rows plus the pandas and pyarrow versions. An entry is
  used only while every field matches; anything else (a re-downloaded day, a code or library change, another
  `schema_version`) is a miss read from the day file and overwritten. A hit returns the same frame as the file:
  columns, dtypes, values, missing fields, row order and `attrs` (`seconds` is the hit's own time). Writes are
  atomic (temp file + rename) and skipped when the day file changed during the read or the drive has under 50 GB
  free. `<root>` is `NOVA_MARKET_READ_CACHE_DIR`, else `F:\Nova\market_read_cache` when F: is mounted on Windows,
  else no cache; `NOVA_MARKET_READ_CACHE=0` turns it off; `NOVA_MARKET_READ_CACHE_GB` (default 50) caps it, the
  least recently used entries (a hit touches its file) deleted down to 90% of the cap, checked on a process's first
  write and every 1 GB it writes. `trades`' `sets_price` is asked once per distinct `(conditions, correction)` pair.
- **Momentum-research tools** (`tools/nova_data_research.py`, the second tool set; CLI `tools/market_data_research.py`):
  - `find_stock_days {filters, symbol?, kinds?, splits?, float_max?, float_basis?, float_unknown?, catalyst?, halted?,
    cursor?, page_size?, output_name?}` -> a table answer plus `next_cursor` (`"YYYY-MM-DD|SYMBOL"` or null). Rows:
    `date, symbol, kind, prev_close, open, high, low, close, volume, dollar_volume, high_pct, low_pct, close_pct,
    gap_pct, day_high, day_high_et, day_low, day_low_et, pm_high, pm_low, pm_volume, ah_high, ah_volume, split,
    up10_et .. up300_et, down10_et .. down50_et, outstanding_shares, outstanding_as_of, outstanding_filed,
    outstanding_age_days, enrichment_float, float_shares, float_source, catalyst_verdict, catalyst_category,
    catalyst_strength, catalyst_title, catalyst_cutoff, halts, first_halt_et, halt_codes, luld_halts`. `filters` are
    `movers_scan`'s (needs `date_from` / `date_to` or `symbol`). `float_basis` `sec_outstanding` (default: the movers
    store's `sec_shares` by `day_movers.floats.sec_shares` -- filed by the day, as of at most 120 days before it,
    split-adjusted; a reused ticker's count is dropped when its CIK is not the day's holder) | `enrichment` (desk
    `archive.db` `enrichment_snapshots`) | `best`; `float_source` is `sec_shares_outstanding` | `enrichment_snapshot`
    | null; `float_unknown` exclude | include | only. `catalyst` keeps the listed verdicts (`unknown` = none);
    `halted` true / false (a day the halt log does not cover has `halts` null and is left out by either). `page_size`
    1-5,000 (1-100,000 with `output_name`); one call examines at most 200,000 movers rows (`meta.note`).
  - `daily_bars {symbol, date_from, date_to, adjust?, as_of?, output_name?}` -> rows `date, volume, open, close, high,
    low, transactions, prev_close, change_pct, gap_pct, high_pct, range_pct` (+ `split_factor` when adjusted); at most
    3 years; `meta.volume_note`, `split_note`, `prev_close_from`, `seconds`. In-process cache only (no file).
  - `market_context {day, symbols?}` -> `{day, lookback, symbols: {SYM: {traded, open, high, low, close, volume,
    transactions, prev_close, change_pct, gap_pct, range_pct, return_5_pct, return_lookback_pct, avg_close_lookback,
    close_vs_avg_pct}}, summary, rules, units, raw, seconds}`; nothing after `day`.
  - `stock_day_stats {symbol, day, rvol_days?, spread?}` -> `{symbol, day, prev_close, prev_close_day, day_bar,
    premarket, first_5min, first_30min, regular, whole_day, vwap, trades, spread, rvol, rules, units, seconds}`; each
    window `{open, high, low, close, volume, bars, transactions, high_time, low_time, range_pct, change_pct,
    high_pct}` or null; `spread.{regular, first_30min}` `{window, median_cents, median_bps, quotes, valid_share}`;
    `rvol {basis_sessions, basis_days, by_minute: {HH:MM: {cum_volume, avg_cum_volume, rvol}}, open5, daily}`;
    `rvol_days` 1-60. Windows are `research/orb`'s; VWAP is labelled approximate (minute typical price).
  - `order_flow {symbol, day, start?, end?, bucket?, output_name?}` -> rows of `trades_flow_v1` summed per bucket
    (1m | 5m | 15m | 30m | 60m | day) with `time_et`, `m` and every builder column (`docs/massive-builders.md`), plus
    `off_pct, retail_buy_pct, retail_sell_pct, mid_pct, sweep_pct, odd_pct, big_pct, block_pct` (percent points of
    `vol`) and `retail_imbalance` (-1..1); `meta.day_total` sums the window.
  - `halts {symbol?, day?, date_from?, date_to?, source?}` -> rows `symbol, session_date, source, code, kind, start_ts,
    start_et, end_ts, end_date, end_et, duration_s, resumed`; needs a symbol or a day / range; `meta.coverage`,
    `covered_from`, `codes`, `warning`.
  - `catalysts {symbol, date_from?, date_to?, at?, sources?, limit?}` -> item rows `item_id, source, publisher,
    published_ts, published_et, title, url, form, sec_items, n_tickers` (Finnhub Benzinga copies excluded by
    `research/catalysts/store.HONEST_CLOCK_SQL`), plus `verdicts` (records `symbol, session_date, cutoff_kind,
    rules_version, verdict, category, strength, title, source, published_et, published_ts, item_id, sources_checked,
    n_items, origin, window_start_et, cutoff_et`) and `verdicts_meta`.
  - `symbols {query?, ticker?, day?, active?, types?, limit?}` -> search rows `ticker, name, cik, active, delisted,
    type, exchange, composite_figi, ticker_reused`; with `ticker`: `{symbol, day, listed, ticker_reused, companies:
    [{cik, name, active, delisted, type, exchange, held_from, held_to, composite_figi, last_updated_utc}], on_day:
    {cik, name, rule, warning}, warning, cik_history: {cik: [rows]}, as_of, rule, source, dump_as_of, notes}`.
  `find_stock_days`, `daily_bars` and `order_flow` write an `output_name` file (`readOnlyHint: false`); the rest are
  read-only. `movers_scan` gains `after` (library only) for the cursor.
- **Tripwire** (`tools/data_access_hook.py`): Cursor `beforeShellExecution` (`{permission: "allow" | "deny",
  user_message, agent_message}`) and Claude `PreToolUse` on Bash (`hookSpecificOutput.permissionDecision: "deny"`).
  Denied: a command naming a raw store (`nova/massive`, `nova/leaderboard`, `catalysts/edgar`, `store/reference`,
  the movers / leaderboard / reference-index SQLite files, SEC's zips, the Massive day-file folders) or running a
  script outside the repo that names one. Passes: the front door's tools, repo code, a code search or git not pointed
  at a data folder, and `# raw-data-ok: <reason>`. Unparseable input allows.

