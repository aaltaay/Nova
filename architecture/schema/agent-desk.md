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
  `renderer:"cold"`.

#### The MCP server's warm renderer (#1062)

`nova_trade_charts` draws warm; the other two chart tools stay one-shot. Owner:
`tools/nova_chart_mcp_warm.py` in the long-lived MCP server process, which starts the
gateway's `nova_chart_warm.py serve --idle-seconds 600` in a Job of its own (the gateway's
`OwnedProcesses`), outside every call's Job. Before each call it asks for the answering
renderer's pid, starting one when none answers (a renderer someone started from a shell is
used and left running). The call then runs `nova_trade_charts.py export --warm` in its own
Job as before, torn down and verified as before.

- The answer's checks: `historical_export.json` and `images/EXPORT_RECEIPT.json` agree, and
  the receipt is a warm one (`ok`, `renderer:"warm"`, `warm_service.pid` an integer,
  `cleanup_errors:[]`, `source_data_mutated:false`, `broker_or_desk_calls:false`) plus the
  same selection-hash, capture and image-hash checks as a one-shot receipt; a one-shot
  receipt never passes as warm, nor a warm one as one-shot. The answer adds
  `renderer:"warm"`, `warm_renderer_pid` and `warm_renderer_started_in_call` (true when the
  server's renderer stopped before the job -- stale code, a crash -- and the export started
  one inside the call's Job, which the call's verified teardown then ended).
- No warm renderer can start: the call draws one-shot and says `renderer:"one_shot"`,
  `warm_error:"WARM_RENDERER_UNAVAILABLE"`.
- Lifetime: the renderer stops itself after 10 idle minutes; the next call closes its Job
  (verified) and starts another. At server exit the server stops the renderer it started,
  waits for it, closes its Job and logs `{"warm_renderer_shutdown": {stopped, verified,
  exit_code, live_descendants}}` to stderr. If the server dies abruptly its Job's
  kill-on-close ends the renderer, whose own Job then ends the browser and `vite preview`.

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
  - `ticker_holders (symbol, cik, held_from, held_to)`: for a ticker two CIKs carry in `sec_shares`, which company
    held it, by date (null dates = open-ended; `tickers.holder_runs`, the rule above; a reused ticker no day can
    be settled for has one row with `cik` null), written with `sec_shares` in one transaction (the export drops
    and recreates the table). `day_movers.floats.sec_shares` -- every share-count read (the agent search's float limit,
    `find_stock_days`, the signal table, the HOD Momo rebuild) -- reads only the holder's count; a day no company
    can be named for has no count (unknown). A store exported before the table existed reads as before and logs it.
  - `splits (symbol, execution_date, split_from, split_to)`: the split list the builder adjusted prices by.
  - `day_facts (session_date, symbol, catalyst_verdict, catalyst_category, catalyst_strength, catalyst_title, halts,
    halt_codes, luld_halts, news_halts, rvol_daily)`: what was known about a movers row beyond its prices, written
    whole in one transaction by `research/movers/export_day_facts.py` through the research front door's one join
    (`market_reads.day_facts.for_pairs`: the catalyst backfill's verdict, the day's halts from the halt log, the
    relative-volume table's `rvol_daily`) -- the backend never reads those research stores. A null is unknown
    (never judged, a day the halt log does not cover, too little volume history); a row with nothing known is not
    written; no table or no row reads unknown. A heavy export (every relative-volume day file): run it outside
    04:00-20:00 ET, again after the movers index, the backfill, the halt log or the relative-volume table changes.
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
    `catalyst` (comma list of verdicts; `unknown` = never judged), `catalyst_category` (comma list, e.g.
    `fda_regulatory`), `catalyst_words` (comma list: the verdict's headline contains any; a text match), `halted`
    (`true` | `false`), `halt_codes` (comma list: `T1`, `LUDP` ...; `news` / `luld` name their groups),
    `rvol_daily_min` (ratio, 5 = 5x the usual whole-session volume) (these six read `day_facts` and filter by
    `day_movers.facts.keep`, the rule `find_stock_days` filters by, so a stock-day passes both searches alike: an
    unknown fact is left out and counted in `excluded` -- `rvol_unknown`, `halts_unknown`, and `day_facts` for
    every row the fact filters left out -- with a note; the answer carries `day_facts: {exported, first, last}`,
    with a note naming the export when it never ran, and each row `day_facts: {catalyst_verdict,
    catalyst_category, catalyst_strength, catalyst_title, halts, halt_codes, luld_halts, news_halts,
    rvol_daily}`), `replayable` (only days whose trades file is on disk), `splits` (`exclude_likely` default | `include` |
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
  - `GET /api/agent/market-temperature?day=YYYY-MM-DD` (ADR 053 amendment 2026-10-25; operator: "we need an
    endpoint for agents and AI to know at any time the output of this feature") -> `{schema_version: 1, day, as_of,
    final, labels: {day: "hot" | "warm" | "cold" | null, week: "good" | "ok" | "choppy" | "cold" | null, month:
    "hot" | "warm" | "cold" | null}, day_detail, week, month, rules: string[]}` -- the Market page's small-cap
    temperature for `day` (default: the current session, so far). `day_detail` / `week` / `month` are the Market
    wire's `climate.heat` (`market-board.md`) for 1 D / 7 D / 30 D ending at `day`, with the same rules and the same
    history window, so an agent reads exactly what the page shows; `as_of` is when it was read (now, or that
    session's close) and `final` is true once the session closed. It reads the leaderboard store whether or not the
    Market page has run: a session Nova does not hold yet is read on the call, today again each call. A day that is
    not an exchange session answers for the session before it (`day` says which). Refusals: `AGENT_INVALID` 400 (not
    `YYYY-MM-DD`, or after today), `AGENT_LEADERBOARD_UNAVAILABLE` 503 (no leaderboard store). Read-only.
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
MCP server (`tools/nova_mcp.py`, official SDK, stdio; registered in `.cursor/mcp.json` and `.mcp.json` as
`nova-data`; `tools/nova_data_mcp.py` starts the same server). Read-only on the data; the catalog, prose and traps are `docs/market-data.md`. The desk chart tools on that server are "Desk review charts (unified MCP)" below.

- **Tools** (each answers a JSON object; a failed read is `{ok: false, error: "<Type>: <message>"}`, never a crash):
  `data_catalog` (`{ok, datasets: [{name, source, history, as_of, units, mcp, cli}], not_here: string[]}` -- call it
  first), `data_status`, `stock_day {kind: trades|quotes|bars, symbol, day, start?, end?, tf?, adjust?,
  fill_gaps?, output_name?}`, `movers_search {params}` (the `/api/agent/movers` answer, at most 500 rows), `movers_scan {filters,
  symbol?, kinds?, columns?, limit?, splits?, output_name?}`, `board {day, at, list_name, source?}`, `splits {symbol,
  day?, cik?}` (`price_factor` with `day`), `financials {symbol, statement, as_of?, timeframe?, cik?}`, `sec_shares
  {symbol, day?, max_age_days?, cik?}`, `sec_filings {symbol, as_of?, forms?, cik?}`, `float_latest {symbol?}`, `ipos
  {symbol?, date_from?, date_to?}`, `ticker_details {symbol}`, `short_interest {symbol, day, at?}`, `cash_runway
  {symbol, day, cik?, lookback_days?}` (below).
- **`stock_day` bars** take `tf` as a count and `s` / `m` / `h`; a daily `tf` (`1d`, `1w`) is refused naming the
  daily bars tool. Minute bars carry Massive's own volume; seconds bars sum every trade except cancel / error
  records (`docs/market-data.md`, "Two volume rules").
- **Bar gaps** (#1086). A bar exists only for a bucket with a trade, so a halt or a quiet stretch is a hole in the
  series, and a consumer plotting by row index would draw it continuous. `reads.bars` (so `stock_day` bars and
  `market_data.py bars`) says where. `meta.gaps` lists the runs of missing buckets inside the window as `{first_et,
  last_et, buckets}`: the window is the asked `start` .. `end` when given, else the first .. last bucket of the read;
  `first_et` / `last_et` are the first and last missing bucket's start, both inclusive, ET `HH:MM` (`HH:MM:SS` for a
  seconds `tf`), in time order. At most 50 runs are listed, the longest ones (`meta.gaps_truncated` true when more
  exist); `meta.gap_runs` and `meta.gap_buckets` count every run and every missing bucket. A gap is a bucket with
  no trade: a halt is one cause (the `halts` tool lists halts, from 2021-09-21), a dead stretch another. A seconds
  bar that had trades but no price-setting print is a row (volume, no prices), never a gap. A read with no row has
  no gap meta. `fill_gaps=true` (CLI `--fill-gaps`; default false, rows unchanged) inserts one row per missing
  bucket: `open` / `high` / `low` / `close` null (no price is invented and none is carried forward), `volume` and
  `transactions` 0, plus a boolean column `filled` (true on the inserted rows, false on the rest); `meta.gaps` is
  the same either way.
- **`movers_scan`** applies the capped search's split rule (`day_movers.query.splits_sql`: `splits` =
  `exclude_likely` default | `include` | `only_suspects`) and its percent-line tolerance (`query.pct_bound`); a row
  selecting `split_listed, split_suspect, prev_volume, volume` (every column does) gains `split` (`listed` |
  `likely_split` | `suspect` | null). It refuses a call without `date_from` / `date_to`, a symbol or a `limit`; a
  `limit` is 1-1,000,000; without one at most 100,000 rows return and `meta.capped` (bool) / `meta.note` say more
  matched. `meta.filters.splits` echoes the choice. `kinds` is a list of types (case-insensitive, `["ETF"]`) or the
  one word `["common"]` / `["all"]` (`day_movers.query.kinds_sql`, the rule `movers_search` applies); omitted it
  keeps every kind, unlike `find_stock_days` (below).
- **`board`** answers `change_pct` / `gap_pct` in percent points (the store keeps fractions) and adds top-level
  `covered` (false when the day has no board, recorded or rebuilt), `gap` (`{start, end, reason, stop}` or null)
  and `note` when not covered. **Coverage differs by list** (`data_status`, 2026-10-20; the counts grow with every recorded session). It counts
  stored boards, not lists, so read it with the rule `reads.LIST_BOARD`: Gainers on a day the desk recorded is the
  recorded `gainers` board (19 sessions, 2026-09-23 on); on every other covered day it is the rebuilt `market` board
  (1,735 sessions, 2016-11-30 .. 2026-09-22), so Gainers has an answer on every board-covered session (1,754;
  #1086 item 7 read the two counts as a gap). `gappers` and `losers` cover those 1,754 from 2016-11-30 and
  `afterhours` 1,753 from 2016-12-01. `large_cap` exists only on the 19 recorded sessions (nothing rebuilds it: no
  market cap as of the day); any other day answers `covered: false` with a note. Never read 0 rows as "no movers".
  The same rule holds for `catalyst_verdict` on `find_stock_days` rows: the backfill judged the Five Pillars gap
  universe from 2021-10-11 to 2026-09-21 and the leaderboard's top-10 movers from 2026-06-17 to 2026-09-21
  (`catalysts` `verdicts_meta.coverage`), so any other stock-day has a null verdict: unknown, never "no news".
- **A ticker two companies used** (`research/market_reads/tickers.py`, over `reference/tickers.json`, tickers matched
  exactly as Massive writes them -- `AAp`, a preferred, is not `AAP`; an asked ticker the list does not hold as
  given is read upper-case, `tickers.key`): SEC shares /
  facts / filings, financials and splits read the company that held the ticker on the asked day (former holder
  until its `delisted_utc` day; today's holder from its ticker-details `list_date`, else the day after the former
  left; overlaps settled by whose SEC filings span the day, then by the only `CS` / `ADRC` candidate, with the
  warning kept). Answers carry `ticker {cik, name, ticker_reused, rule,
  warning, candidates: [{cik, name, held_from, held_to}]}` (`meta.ticker` on tables). A day that cannot be settled
  is `{ok: false, error: "LookupError: ... could be A or B: pass cik="}`; `cik` reads one company. Without a day
  the read is today's holder with `warning` naming the others. `splits` without `day` adds `holder_cik` per row
  for a reused ticker; financials keep only statements whose own `cik` is the holder's.
- **A table answer** is `{ok: true, meta, rows, columns, data, truncated, out}`: `rows` matched, `data` the first 200
  as records (a time with a zone keeps its own offset: `time_et` is `2026-09-03T09:40:00-04:00`, never the UTC
  `...13:40:00.000Z` pandas would write, #1086), `meta` the read's attributes (its as-of rule, units, source). `output_name` (a new plain
  `*.parquet` / `*.csv` name) writes every row under `--output-root` (default `<temp>/nova-data-mcp`) and `out` names
  it; an existing name or a path is refused. Only `stock_day` and `movers_scan` write (`readOnlyHint: false`,
  `destructiveHint: false`); every other tool is `readOnlyHint: true`.
- **`sec_shares` with `day`** is `{symbol, day, cik, entity, rule, outstanding, issued, treasury, public_float_usd,
  filer}`; each value `{value, concept, end, filed, form, age_days}` or null -- the newest fact filed on or before
  `day` whose period `end` is on or before it. `outstanding` is the cover page's `EntityCommonStockSharesOutstanding`,
  else the balance sheet's `CommonStockSharesOutstanding`, times `split_factor` (splits executed after `end` through
  `day`); `max_age_days` nulls an older one. `public_float_usd` is the 10-K's `EntityPublicFloat` (dollars). `filer`
  is `domestic` (newest annual report filed by `day` a 10-K), `foreign` (20-F / 40-F) or `unknown`.
- **`cash_runway {symbol, day, cik?, lookback_days?}`** (#1102; operator 2026-10-20: "no cash runway or dilution
  risk"; owner `research/market_reads/runway.py`; CLI `market_data.py runway SYMBOL DAY`): the cash, the operating
  cash flow, the share count and the offering filings a company had on file by `day`, composed from `financials`,
  `sec_shares` (`sec.shares_as_of`) and `sec_filings` and nothing else (no new reader of a raw store). It is one
  method, so agents' numbers agree. Answer `{ok, symbol, day, cik, entity, ticker, rule, units, cash, burn, runway,
  shares, offerings, notes}`. Every figure sits in a block that names its statement: `period_end`, `filing_date`,
  `age_days` (`day` minus `period_end`) and `stale` (`age_days` over 180, two quarters). A figure the files do not
  give is `null` and its block says why; never 0. The wording is neutral: counts, dates and ratios, no verdict.
  - **Dates.** A statement or filing counts from the day it was filed (the stated day included). A statement is
    dropped when its `period_end` is after `day` or after its own `filing_date` (a filing cannot report a period
    that had not ended; `notes` counts them). Massive dates a statement by the newest filing that carried the
    period, so 300 or more days after `period_end` for 87% of quarterly cash-flow rows and 27% of balance sheets
    (every year 2016-2026): on a past day the newest statement known is often over a year old, and a balance sheet
    can be newer than the newest cash-flow quarter. `stale` and `notes` say so; the read never fills the gap.
  - **`cash`**: the newest balance sheet filed by `day` (either timeframe: newest `period_end`, then `filing_date`),
    `{cash_and_equivalents, short_term_investments, liquid, liquid_basis, timeframe, period_end, filing_date,
    age_days, stale}`, or null. `liquid` = `cash_and_equivalents` + `short_term_investments`; with no short-term
    investments reported it is `cash_and_equivalents` and `liquid_basis` says so; null when cash is not reported.
  - **`burn`**: the newest quarterly cash-flow statement filed by `day`, `{operating_cash_flow, burn, field,
    fiscal_year, fiscal_quarter, period_end, filing_date, age_days, stale, recent_quarters}`, or null. Massive's
    quarterly rows are stand-alone quarters (a fiscal Q4 row too; AMC 2022's four sum to its annual).
    `operating_cash_flow` is signed as filed: `net_cash_from_operating_activities`, else
    `cash_from_operating_activities_continuing_operations` (`field` names which). `burn` = the cash used
    (`-operating_cash_flow`) when that is negative, else null. `recent_quarters` is up to four quarterly rows
    newest first, `{period_end, filing_date, operating_cash_flow}`.
  - **`runway`**: `{months, status, stale, basis, period_gap_days, max_period_gap_days}`. `months` = `cash.liquid` /
    (`burn.burn` / 3), one decimal. `period_gap_days` = `cash.period_end` minus `burn.period_end`; beyond +/- 14
    (`max_period_gap_days`) the two are not the same fiscal period and `months` is null, so a balance sheet one quarter
    newer than the newest cash-flow quarter (about 91 days) is refused, never divided. Of Massive's quarterly cash-flow
    rows 94.7% have a balance sheet with the exact same `period_end`; the other matches are days apart (52/53-week
    years) and the next nearest period is 84 or more days away. `stale` is true when the cash or the burn it is built from is stale (null when
    there is neither): a `computed` runway built from old statements is still a number about those quarters, so a
    filter on `months` should read `stale` beside it. `status`: `computed`, `no_burn` (operating cash flow zero or
    positive), `no_balance_sheet`, `no_cash_flow_statement`, `cash_not_reported`, `operating_cash_flow_not_reported`,
    `periods_differ`. `burn` and `cash` stay in the answer either way.
  - **`shares`**: `{outstanding, growth_4q, growth_8q}`. `outstanding` is `sec_shares`' (`{value, concept, end,
    filed, form, age_days, split_factor}`, split-adjusted to `day`) or null. `growth_4q` / `growth_8q` =
    `{pct, status, months_back (12 | 24), from, to, span_days}`: `to` is that count; `from` is the same read for the
    day `months_back` earlier (`{value, end, filed, form}`), put on `day`'s share basis by dividing by
    `splits.factor(prior_day, as_of=day)`; `pct` = (`to` / `from` - 1) x 100 percent points; `span_days` is the days
    between their `end`s. `from.value` is rounded like `outstanding`. `status`: `computed`, `no_count_now`,
    `no_count_then`, `same_count` (no newer count was filed in the window, so growth is unknown, not 0),
    `span_off_window` (`span_days` is more than 100 days from `months_back` x 30.4375 -- the window plus or minus a
    filing lag, a separate tolerance from the runway's 14 days -- e.g. a filing gap such as a
    cover page that gives each share class its own count, which SEC's facts omit; `pct` null, `from` / `to` kept),
    `count_then_not_positive`.
  - **`offerings`**: the registration and prospectus filings and current reports filed in the `lookback_days` before
    `day` (default 1095, the dilution row's longest window; 1-3650), or null when SEC has no submissions list for the
    company (`notes` says so): `{lookback_days, from, through, forms, total, counts: {form: n}, latest: {form: filed},
    filings: [{form, kind, filed, report_date, accession, items}], truncated}`. `filings` is newest first, at most
    100 (`truncated`); `counts` and `latest` cover all of them. Forms: S-1, S-1/A, S-3, S-3/A, S-3ASR, F-1, F-1/A,
    F-3, F-3/A, F-3ASR, 424B1 .. 424B5, 8-K. `kind`: `s1` (S-1, F-1), `shelf` (S-3, F-3), `prospectus` (424B1-5),
    `current_report` (8-K); an 8-K's `items` is SEC's list ("3.02,9.01"), not read further. A filing says it was filed,
    not that an offering priced or closed. The stock read's "Dilution on file" row (`stock-read.md`) uses the same form
    families with its own windows and counts 424B1-8; this read is the history behind it.
  - **`units`**: amounts are the statements' own; the dump carries no currency field, so a foreign filer reporting in
    another currency reads in it (`months` and `pct` do not depend on it). Shares are shares; `pct` is percent points.
    A reused ticker reads the company that held it on `day` (`ticker`); an unsettled day errors with the candidates.
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
- **Windowed reads** (#1062, `reads._parse_window`): a read with `start` and/or `end` that the read cache does not
  hold parses only the window's lines and is not saved (the cache keeps whole days). pyarrow first reads the block's
  non-text columns: the time column picks the lines (no row order is assumed), and each column's type and gaps over
  the whole block give the window the dtype the whole-day parse gives (a whole-number column with a gap or a
  fraction anywhere that day is float64). The frame is the whole-day read cut to the window: columns, dtypes,
  values, missing fields, row order and `attrs`. A window with no row, a time that is not a whole number on every
  line, or a non-text column that is not a number somewhere that day is read the whole-day way (and cached).
- **Momentum-research tools** (`tools/nova_data_research.py`, the second tool set; CLI `tools/market_data_research.py`):
  - `find_stock_days {filters, symbol?, kinds?, splits?, float_max?, outstanding_max?, float_basis?, float_unknown?,
    catalyst?, catalyst_category?, catalyst_words?, halted?, halt_codes?, rvol_daily_min?, market_cap_min?,
    market_cap_max?, sort?, limit?, cursor?, page_size?, output_name?}` -> a table answer plus `next_cursor`
    (`"YYYY-MM-DD|SYMBOL"` or null). Rows:
    `date, symbol, kind, prev_close, open, high, low, close, volume, dollar_volume, high_pct, low_pct, close_pct,
    gap_pct, day_high, day_high_et, day_low, day_low_et, pm_high, pm_low, pm_volume, ah_high, ah_volume, split,
    up10_et .. up300_et, down10_et .. down50_et, outstanding_shares, outstanding_as_of, outstanding_filed,
    outstanding_age_days, enrichment_float, float_shares, float_source, catalyst_verdict, catalyst_category,
    catalyst_strength, catalyst_title, catalyst_cutoff, halts, first_halt_et, halt_codes, luld_halts, news_halts,
    rvol_daily, rvol_volume, rvol_day_avg_volume, rvol_day_avg_sessions, market_cap`. **Market cap** (operator
    2026-10-26): `market_cap` is an estimate, `prev_close` (the prior close, already on the day's share basis) x
    `outstanding_shares` (SEC shares outstanding known that day), rounded to the dollar -- never the board's or a
    vendor's market cap; null when either is unknown. `market_cap_min` / `market_cap_max` (dollars; min over max is
    refused) keep the rows inside; a row with `market_cap` null is left out and counted in
    `meta.left_out.market_cap_unknown`, never read as small; `meta.market_cap_rule` says the rule. **One join** (search gaps, operator
    2026-10-26): every column after the marks comes from `research/market_reads/day_facts.py` (`for_pairs`), the one
    join of shares, catalyst, halts and relative volume that `find_stock_days`, the relative-volume tools and the day
    facts export (`/api/agent/movers`) all use, and every row filter is `day_movers.facts.keep` -- so a stock-day
    passes or fails a filter the same way in each. `news_halts` counts the news halts (T1-T3, T12), `luld_halts`
    the LULD / volatility pauses; both null with `halts` on a day the halt log does not cover. `halt_codes` (filter)
    keeps a day with a halt of any listed code (`T1`, `LUDP` ...; case ignored) or of a named group (`news`,
    `luld`); an uncovered day is left out and counted in `meta.left_out.halts_unknown` (so is one `halted` leaves
    out). `meta.left_out` counts every unknown a filter dropped: `catalyst_unknown` (no verdict, under a news
    filter), `shares_unknown` (no value on the basis, under `float_unknown` exclude), `rvol_unknown`,
    `halts_unknown`. **News and volume filters** (#1100 table, operator
    2026-10-25): `catalyst_category` keeps the verdict's category (`fda_regulatory`, `clinical_data` ...; case
    ignored); `catalyst_words` keeps a `catalyst_title` containing any of the words (case ignored; a text match, not
    a judgment); `rvol_daily` is the stock-day's 04:00-20:00 volume over the relative-volume table's
    `day_avg_volume` (`research/market_reads/rvol_days.py`, rounded to 0.01; `rvol_scan`'s `rvol_daily` at the
    session's end), null when the table does not hold the stock-day or `rvol_day_avg_sessions` is under 20 --
    unknown, never low; `rvol_daily_min` (a ratio over 0, 5 = 5x) keeps rows at or over it, leaves the unknowns out
    and counts them in `meta.left_out.rvol_unknown` (`meta.rvol_rule` says the rule). `filters` are
    `movers_scan`'s (needs `date_from` / `date_to` or `symbol`). `float_basis` `sec_outstanding` (default: the movers
    store's `sec_shares` by `day_movers.floats.sec_shares` -- filed by the day, as of at most 120 days before it,
    split-adjusted; a reused ticker reads only its holder's count, `ticker_holders`) | `enrichment` (desk
    `archive.db` `enrichment_snapshots`) | `best`; `float_source` is `sec_shares_outstanding` | `enrichment_snapshot`
    | null; `float_unknown` exclude | include | only. `catalyst` keeps the listed verdicts (`unknown` = none);
    `halted` true / false (a day the halt log does not cover has `halts` null and is left out by either). `page_size`
    1-5,000 (1-100,000 with `output_name`); one call examines at most 200,000 movers rows (`meta.note`).
    **`kinds` defaults to common stock** (#1086 item 3): omitted, the rows are `movers_search`'s `common` kinds
    (`day_movers.query.kinds_sql`: `kind` `CS` or `ADRC`, or an unlabelled symbol of at most four letters), so
    warrants, rights, units, preferreds and ETFs are out (Sep 2026: 15,687 `CS` and 1,209 `ADRC` rows beside 3,288
    `WARRANT`, 616 `RIGHT`, 6,173 `ETF`). A list of types keeps those (`["ETF"]`, `["CS", "WARRANT"]`; case does not
    matter), `["all"]` keeps every kind, `["common"]` is the default spelled out; `all` / `common` with other items is
    refused. A call that names a `symbol` and no `kinds` keeps every kind (the ticker is the filter, as the desk's own
    symbol lookup does; a warrant's days must not come back empty). `meta.filters.kinds` echoes the rule used
    (`common`, `all` or the types) and `meta.kinds_rule` says it in words. The CLI takes `kinds=common`,
    `kinds=all` or `kinds=CS,ETF`.
    **`sort` ranks the answer** (#1086 item 2): the choices are `movers_search`'s (`day_movers.query.SORTS`) --
    `newest`, `oldest` (default: the order pages always had, day ascending then symbol), `high`, `close`, `gap`,
    `volume`, `dollar_volume` (largest first), `low` (deepest first) -- with a row missing the figure last and ties
    newest day first, then symbol (`query.sort_rows`; the rows missing the figure are ordered the same way, so
    `movers_search` and `find_stock_days` agree on them too). The movers store orders the rows (`ORDER BY`); each chunk is
    then enriched and filtered in that order, so `float_max`, `catalyst` and `halted` pick from the ranking and
    `limit` 10 under `sort: "high"` is the ten largest highs that pass them. Pages stay exact: `next_cursor` is still
    `"YYYY-MM-DD|SYMBOL"`, the last row examined, and the next call (same arguments plus `cursor`) resumes strictly
    after that row in the same ordering (a keyset on the sort column, then day, then symbol), so pages add up to the
    whole ranked answer without a repeat or a hole. A `cursor` naming a row the search does not hold is refused.
    `limit` is `page_size` under the name `movers_search` uses (1-5,000; 1-100,000 with `output_name`; both given and
    unequal is refused), and `next_cursor` still continues the ranking past it. `meta.filters.sort` echoes the choice.
    **`outstanding_max`** (#1086 item 6) is `float_max` named for what it filters: SEC shares OUTSTANDING (insiders
    and locked-up shares inside), never free float. It needs `float_basis` `sec_outstanding` (the default; `enrichment`
    or `best` is refused, use `float_max`), and passing it with `float_max` is refused. `meta.filters` echoes the one
    passed. `movers_search`'s `float_max` is a proof on either the desk's float (when it had one) or SEC shares
    outstanding (`day_movers.floats`): `float_basis` `best` is the nearest here.
  - `daily_bars {symbol, date_from, date_to, adjust?, as_of?, output_name?}` -> rows `date, volume, open, close, high,
    low, transactions, prev_close, change_pct, gap_pct, high_pct, range_pct` (+ `split_factor` when adjusted); at most
    3 years; `meta.volume_note`, `split_note`, `prev_close_from`, `seconds`. In-process cache only (no file). Two
    sessions meet in one row (#1086 item 5): `volume` is the whole 04:00-20:00 session, `open` / `high` / `low` /
    `close` are regular hours only (Massive's day files), so a bar can hold volume that built a range it does not
    show -- FLYE 2026-09-01 has `high` 2.79 while `find_stock_days` reports `day_high` 3.97 at 05:38 ET (premarket).
    A bar's regular-hours volume is not in this table: `stock_day_stats` splits premarket, regular and whole-day.
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
  - `halts {symbol?, day?, date_from?, date_to?, source?, codes?}` -> rows `symbol, session_date, source, code, kind,
    start_ts, start_et, end_ts, end_date, end_et, duration_s, resumed`; needs a symbol or a day / range;
    `meta.coverage`, `covered_from`, `codes` (what each code means), `warning`. `codes` keeps the halts of those codes
    (`halts.code_matches`: a code or IBKR kind as written, case ignored, or the groups `news` -- T1-T3, T12 -- and
    `luld` -- LULD and volatility pauses, IBKR's `luld` included); `meta.asked.codes` echoes them.
  - `catalysts {symbol, date_from?, date_to?, at?, sources?, limit?}` -> item rows `item_id, source, publisher,
    published_ts, published_et, title, url, form, sec_items, n_tickers` (Finnhub Benzinga copies excluded by
    `research/catalysts/store.HONEST_CLOCK_SQL`), plus `verdicts` (records `symbol, session_date, cutoff_kind,
    rules_version, verdict, category, strength, title, source, published_et, published_ts, item_id, sources_checked,
    n_items, origin, window_start_et, cutoff_et`) and `verdicts_meta`.
  - `news_search {date_from, date_to, verdict?, category?, words?, scope?, sources?, limit?, output_name?}` -- news
    across every stock, no symbol (search gaps, operator 2026-10-26: "every FDA headline on day X"). Both days
    required, at most 366 days apart. `scope` `verdicts` (default, `catalysts.search_verdicts`): the newest-rules
    verdict rows (the `verdicts` columns above), newest day first, kept by `verdict` (catalyst | negative |
    routine_only | noise_only | none_found), `category` (case ignored) and `words` (the deciding headline contains
    any; a text match); `meta.categories` counts every category in the range before the filters (the values
    `category` takes), `meta.matched` the rows before `limit`. `scope` `items` (`catalysts.search_items`): every
    headline containing any of `words` (required), one row per item and stock it names (`symbol` first, then the
    item columns), newest first, Finnhub Benzinga copies excluded; `verdict` / `category` are refused there. Only
    the backfill's target stock-days have verdicts and only its tickers have items: a stock-day in no row is
    unknown, never no news. At most 5,000 rows (`limit`; `meta.truncated` for items); `output_name` writes them.
    CLI `market_data.py news --from --to [--verdict] [--category] [--words] [--items] [--sources] [--limit]`.
  - `symbols {query?, ticker?, day?, active?, types?, limit?, exchange?, cik?}` -> search rows (`exchange` the
    primary exchange, e.g. `XNAS`; `cik` every ticker a company used) `ticker, name, cik, active, delisted,
    type, exchange, composite_figi, ticker_reused`; with `ticker`: `{symbol, day, listed, ticker_reused, companies:
    [{cik, name, active, delisted, type, exchange, held_from, held_to, composite_figi, last_updated_utc}], on_day:
    {cik, name, rule, warning}, warning, cik_history: {cik: [rows]}, as_of, rule, source, dump_as_of, notes}`.
  - `journal_trades {symbol?, setup?, tag?, adherent?, date_from?, date_to?, limit?, include_mock?, output_name?}`
    (operator 2026-10-26) -> the operator's own trades from the desk's journal (`research/market_reads/journal.py`):
    `journal.db` found by `roots.cache_store` (`NOVA_CACHE_DIR`, else the main checkout's `backend/.cache`, then
    `F:\Nova\cache`) and filtered by `journal.store.get_trades` -- the rule `GET /api/journal/trades` uses -- on a
    read-only connection (`database=`), so the journal is never created, migrated or written; a journal not on disk
    is a `LookupError` naming the folders looked in. Rows `id, opened_et, closed_et, symbol, setup, side, qty,
    entry_price, exit_price, stop_price, target_price, pnl, commission, adherent, tags, notes, is_mock, opened_ts,
    closed_ts`, newest first; `limit` default 200, 1-10,000; mock rows only with `include_mock`. `meta.summary`
    `{trades, closed, pnl, wins, losses, commission}` sums the rows returned, `meta.journal_rows {real, mock}` counts
    the file, and `meta.not_here` says the desk's fills are not here (the Account page reads `GET
    /api/practice/history` and IBKR's closed orders). The operator's journal held 0 real and 12 mock rows on
    2026-10-26. CLI `market_data.py journal [--symbol --setup --tag --adherent yes|no --from --to --limit
    --include-mock]`.
  `find_stock_days`, `news_search`, `journal_trades`, `daily_bars` and `order_flow` write an `output_name` file (`readOnlyHint: false`); the rest are
  read-only. `movers_scan` gains `after` (library only) for the cursor.
- **Across every stock: filings, short interest, sector** (search gaps, operator 2026-10-26; tools
  `tools/nova_data_scans.py`, CLI `tools/market_data_scans.py`, reads `research/market_reads/sec_scan.py` and
  `reference_scans.py`; each takes a heavy-read slot and writes an `output_name` file when asked):
  - `sec_filings_scan {forms, date_from, date_to, tickers?, ciks?, sic?, output_name?}` answers who filed a form
    across companies. `forms` is required and matched exactly as SEC writes them, asked in any case (`S-1` is not
    `S-1/A`); `date_from` .. `date_to` (filing dates) span at most 31 days, anything wider is refused. It reads SEC's
    `submissions.zip` one company at a time for every company in Massive's ticker list, active and delisted; a filer
    that never held a ticker Massive lists is read only when `ciks` names it. Rows `filed, accepted_et, form, ticker,
    tickers, cik, company, sic, accession, report_date, items, accepted_clock`: a filing counts from its filing date;
    `accepted_et` is SEC's acceptance time placed on its own clock by the catalyst backfill's rule
    (`research/catalysts/edgar_clock.py`, `placed`), `accepted_clock` says what placed it. `ticker` is the ticker the
    company held on the filing day (null before its listing or after its delisting; a reused ticker only on days it
    was this company's), `tickers` every ticker Massive gives the CIK (case kept), and each row is its own company
    (`cik`), never merged. `tickers` (the company that held each on both ends of the span; a day the list cannot
    settle is refused), `ciks` or `sic` (SEC's code today; `283*` is a prefix) narrow the read. Measured on the
    operator's zip: a week about 7 s, a broad form over a month up to about 18 s, a server's first SEC read about
    10 s more. `meta.scanned` counts the companies read, parsed and skipped.
  - `short_interest_scan {settlement? | day? + at?, min_shares?, min_days_to_cover?, kinds?, sort?, output_name?}`
    lists every stock's FINRA short interest at one settlement, optionally at least `min_shares` short and / or
    `min_days_to_cover` (`days_to_cover` 999.99 is FINRA's cap). The settlement is the one named, or the newest
    published by `day` (ET `at`, default 09:30) under `short_interest`'s publish lag (`move_reason.short_interest.
    counts_from`: the 8th business day after settlement); `meta.picked` names it and the newer one still pending.
    Every row is from that one settlement: a stock missing from it is missing, never read from an older one. Rows
    `ticker, cik, company, type, settlement_date, short_interest, avg_daily_volume, days_to_cover, counts_from,
    ticker_warning`; tickers stay as FINRA writes them (`ABRpD`, a preferred), each row naming the company that held
    the ticker on the settlement day. Common stock by default; `kinds=["all"]` keeps ETFs, preferreds and OTC names
    Massive does not type; `meta.left_out` counts `other_kind` / `unknown_kind`. `sort` `short_interest` (default)
    | `days_to_cover` | `ticker`. A settlement not on file, or `settlement` with `day`, is refused. The month files
    hold data from 2017-12 (2016-01 .. 2017-11 are empty on disk).
  - `sector_scan {sic?, sic_words?, exchange?, active?, kinds?, output_name?}` lists every listed company in an
    industry: SIC codes (`2834`, or `283*` for a prefix) or words in the SIC description (any word, any case; codes
    and words combine with OR), optionally by primary exchange and `active`. Rows `ticker, name, cik, sic,
    sic_description, exchange, list_date, type, active`. Common stock by default; `kinds=["all"]` keeps warrants,
    units and preferreds. SIC comes from Massive's ticker details, the reference dump's latest value (not as of a
    past day; `meta.note`), and the dump has ticker details only for tickers active when it was taken (13,901 rows,
    6,032 with a SIC), so a delisted company is not in this scan.
  The per-stock `short_interest` reads the ticker as written first and upper-cases it only when that has no row,
  never mixing the two (FINRA's `ABRpD` is another security than `ABRPD`); `symbols` rows show a ticker as Massive
  writes it (`AAp`, never `AAP`).
- **Relative volume across every stock, and what came next** (#1100, operator 2026-10-20: "agents using standardized
  methods ... access to a large sum of data, standardized in the way they access this data"; tools
  `tools/nova_data_rvol.py`, CLI `tools/market_data_rvol.py`, reads `research/market_reads/rvol.py` and
  `rvol_outcomes.py`, builder `research/rvol/build_rvol.py`):
  - **The table** (owner `research/market_reads/rvol_store.py`; invalidation: a day whose minute file, day file or
    movers session changed since it was built, a split-table change, or a `builder` bump stales that day and every
    later one -- a baseline reads earlier days). Root `NOVA_RVOL_DIR`, else `F:\Nova\rvol` when F: is mounted on
    Windows, else `<NOVA_MARKET_DATA_DIR>/rvol`. `manifest.json` `{schema_version: 1, builder, kinds, rules,
    splits_fingerprint, days: {YYYY-MM-DD: {minute_file: {size, mtime_ns}, day_file: {size, mtime_ns},
    movers_built_ts, stock_days, bars, built_ts, seconds}}}`, replaced atomically after each day; another
    `schema_version` refuses (`UnknownRvolSchema`). Two Parquet files per session (zstd; file metadata `nova_rvol`
    `{schema_version, builder, day, table}`), both raw prices, never split-adjusted except where named:
    `minutes/YYYY/YYYY-MM-DD.parquet` -- one row per minute bar starting 04:00-20:00 ET of a symbol of the table's
    kinds: `date` (date), `symbol`, `m` (int16, the bar's start, minutes after ET midnight: 240..1199), `high, low,
    close` (float64, Massive's minute file as delivered), `cum` (float64, the stock-day's volume of bars starting
    04:00 through `m`; a bar's own volume is `cum` less the bar before it), `base` (float32, the mean of the baseline
    sessions' `cum` through `m`; null with no
    baseline session), `vol5` (float32, volume of bars starting in `(m-5, m]`), `base5` (float32, the baseline
    sessions' mean of the same five minutes). Row groups are the bands 04:00-07:00, 07:00-09:30, 09:30-10:00,
    10:00-12:00, 12:00-16:00, 16:00-20:00, each sorted by `symbol, m`. `days/YYYY/YYYY-MM-DD.parquet` -- one row per
    stock-day of those kinds (a day-file row or minute bars): `date, symbol, kind` (`CS` | `ADRC` | `unknown`: the
    type of the company that held the ticker that day in Massive's ticker list; `unknown` when unlisted or untyped),
    `prev_date, prev_close` (the day file's close of the symbol's previous session within 31 days, times the listed
    split factor through the day), `split` (`listed` | `likely_split` | null: the movers store's own rule,
    `day_movers.query`), `day_open, day_high, day_low, day_close, day_volume` (the day file, raw; the finished day),
    `bars, first_m, last_m, hi, hi_m, lo, lo_m, rth_close, last_close, pm_volume, volume` (minute bars 04:00-20:00:
    `rth_close` the close of the last bar starting before 16:00, `pm_volume` bars before 09:30, `volume` their sum),
    `base_sessions` (0-20), `day_avg_volume` (the mean `volume` of the prior day-average sessions) and
    `day_avg_sessions` (0-50), `epoch` (int32), `basis` (float64), `reset` (null | `first_seen` | `holder_changed`
    | `likely_split`). Kinds kept: `CS`, `ADRC`, `unknown` (ETFs, warrants, units, rights and preferreds are not in
    the table).
  - **Baseline sessions:** the symbol's earlier rows in the table with the same `epoch`, at most 20 (minute
    baselines) / 50 (`day_avg_volume`), none more than 100 calendar days before the day. A session before a listed
    split counts on the day's share basis (its volume x `basis` today / `basis` then). `epoch` starts again
    (`reset`) the first time a symbol is seen, when the company holding the ticker changes (`tickers.resolve`), and
    on a likely unlisted split -- its earlier volume is another share basis nobody listed.
  - **Three measures**, each as of the end of a minute (bars starting at or before it; at a clock time `HH:MM`, the
    bars starting before it); a zero or missing baseline is a null measure, never infinite:
    `rvol` (cumulative by minute) = `cum / base`; `rvol_5m` (the scanner's 5-minute column) = `vol5 / base5`;
    `rvol_daily` (the daily rate, "5x the 50-day average") = `cum / day_avg_volume`.
  - `rvol_scan {at, filters, measure?, kinds?, splits?, min_base_sessions?, sort?, limit?, output_name?}` -> a table
    answer, one row per stock-day as of `at` (ET `HH:MM`): `date, symbol, kind, prev_close, at, price, price_et`
    (the close of the last bar starting before `at`, and that bar's start), `change_pct` (percent points vs
    `prev_close`), `volume, base_volume, rvol, volume_5m, base_5m, rvol_5m, day_avg_volume, rvol_daily,
    base_sessions, day_avg_sessions, split`. At a minute with no bar the baselines are computed from the baseline
    sessions' own bars before `at` (the same rule, so a bar minute agrees with `minutes.base`).
  - `rvol_triggers {rvol_min, measure?, window_from?, window_to?, filters?, kinds?, splits?, min_base_sessions?,
    fresh?, limit?, output_name?}` -> one row per stock-day: the first bar starting in `[window_from, window_to)`
    (default 04:00-16:00) where the measure is at least `rvol_min` and every filter holds at that bar: `date, symbol,
    kind, prev_close, trigger_et` (the bar's start), `entry_et` (its end: the first moment it is known), `price` (its
    close), `change_pct, volume, base_volume, rvol, volume_5m, base_5m, rvol_5m, day_avg_volume, rvol_daily,
    above_before` (the measure was over the line on a bar before the window opened, so the window's first bar
    triggered; `fresh: true` leaves those stock-days out), `base_sessions, split`. `filters` keys: `date_from,
    date_to, symbol, price_min, price_max, volume_min, change_min, change_max` (`rvol_scan` adds `rvol_min,
    rvol_max`); a call names both dates or a symbol.
  - `rvol_outcomes {filters, at? | trigger?, up_pct?, down_pct?, horizon?, days?, group_by?, buckets?, measure?,
    kinds?, splits?, min_base_sessions?, control?, seed?, output_name?}` -> `{ok, entries, summary, control,
    meta, out}`. Entries come from `rvol_scan` at `at` or from `rvol_triggers` (`trigger` holds `rvol_min` and
    optionally `measure, window_from, window_to, fresh`).
    Entry price `P` = the close of the last bar starting before the entry clock (`at`, or `entry_et`); only bars
    starting at or after it are read. `horizon` `close` (bars before 16:00), `session` (before 20:00) or `days`
    (`days` 1-20: the rest of the session, then the table's next `days` trading sessions -- the symbol's `hi` /
    `lo` on each it traded, on the entry day's basis; a reset or a likely split inside leaves the entry out as
    `horizon_reset`, sessions past the table's last built one as `horizon_open`). `outcome`: `up` (a bar's high
    reached `P x (1 + up_pct/100)` first), `down` (a low reached `P x (1 - down_pct/100)` first), `same_bar` (both in
    one minute bar: the order is not known and never guessed), `same_day` (both in one later session, `days` only),
    `neither`. `summary` rows per group (`group_by` `rvol` buckets on `measure` -- `buckets` edges, default 0, 1, 2,
    3, 5, 10, 20, 50, 100, 1000 -- or `year`, `hour`, `none`): `group, entries, up, down, same_bar, same_day,
    neither, p_up, p_down` (shares of entries), `p_up_resolved` (up / (up + down)), `median_max_up_pct,
    median_max_down_pct, median_end_pct, mean_end_pct, median_minutes_to_up, median_minutes_to_down`. `control`
    (trigger entries, on by default): one stock-day per trigger from the same date with the same kinds, price,
    split and baseline filters and a bar before the entry clock, that had not met the trigger by then (one over the
    line before the window opened counts as having met it), picked by a seeded hash
    (`seed`, default 1), scored from the same clock the same way -- the same summary shape. `meta` counts what was
    left out (`no_price`, `split`, `base_sessions`, `horizon_reset`, `horizon_open`) and states every rule. Only `output_name`
    writes (each entry with its outcome); the three tools take a heavy-read slot.
  - **News, shares and halts** (search gaps, operator 2026-10-26): `rvol_scan`, `rvol_triggers` and `rvol_outcomes`
    take find_stock_days' day-fact filters through the same join and row filter (`research/market_reads/day_facts.py`
    and `day_movers.facts.keep`, applied by `research/market_reads/rvol_facts.py`): `catalyst` (verdicts; `unknown`
    = a day never judged), `catalyst_category`, `catalyst_words`, `float_max` on `float_basis` (`sec_outstanding`,
    the default: SEC shares outstanding, not free float | `enrichment` | `best`) with `float_unknown` (exclude |
    include | only), `halted`, and `halt_codes` (`T1`, `LUDP` ...; `news` / `luld` name their groups). The facts
    are joined only when a filter or group asks for them, only the parts asked (shares, catalyst, halts), and only
    for the stock-days the relative-volume filters already kept, so a call without them answers exactly as before.
    A kept row carries the joined parts' columns (`catalyst_*`; `float_shares`, `float_source`, `outstanding_*`,
    `enrichment_float`; `halts`, `first_halt_et`, `halt_codes`, `luld_halts`, `news_halts`), and `meta.day_facts`
    echoes the filters, the parts joined, the rows examined and the rules. An unknown never passes a filter that
    asks about it: it is left out and counted in `meta.left_out` (`catalyst_unknown`, `shares_unknown`,
    `halts_unknown` -- the counts `day_movers.facts.keep` keeps for every reader), never read as no news, a small
    float or no halt. In `rvol_outcomes` the filters narrow the entries and the control pool alike (the same
    universe), and `group_by` adds `catalyst` (the verdict), `catalyst_category` (lower case; `no category` for a
    judged day without one) and `float` (`float_shares` on the basis: `<5M`, `5-10M`, `10-20M`, `20-50M`, `50M+`,
    each from its lower edge up to the next, plus `unknown`; `meta.float_buckets`); a stock-day with no value is in
    `unknown`, and each control is grouped with its trigger. `rvol_scan` with a `limit` cuts ties at the limit by
    day, then symbol (identical calls return identical rows).
- **The Trader's signals on past days, and mixing them** (operator 2026-10-20: "I really need a way where we can mix
  and match these signals, so we can iterate through which signals we can use to actually trade and watch for";
  tools `tools/nova_data_signals.py`, CLI `tools/market_data_signals.py`, reads `research/market_reads/signals.py`
  and `signal_outcomes.py`, the list `research/market_reads/signal_registry.py`, builder
  `research/signals/build_signals.py`):
  - **One rule, the desk's.** Every signal is the Trader's Signals panel row (`backend/stock_read/rows.py`,
    `read._verdict`, `plan_liquidity.read`, `history.runs`, `strategy.five_pillars`, `move_reason.rules.read`, the
    setup scanner's lanes through `eyes.replay.EyesReplay` on the built-in templates, `setup_scanner.tape_flow`)
    called with the facts as they stood at the end of each minute -- never a second copy of a rule. A fact with no
    history is `unknown` with its reason (the panel's own word), never guessed: borrow, Level 2 depth (the
    liquidity book walk), HOD Momo's decisions (`hod_now`) and a float as of the day (SEC shares outstanding stand
    in; see `float`).
  - **The universe, point in time.** A stock-day is in the table when the relative-volume table holds it as `CS` or
    `ADRC`, `prev_close` $1-$20, not a likely split, with at least 20 baseline sessions, and some bar starting
    04:00-15:59 ET closed at least 10% over `prev_close` or had `cum / base` at least 5, with at least 50,000 shares
    traded since 04:00 (`cum`). `in_play_m` is the first
    such bar's start; rows exist only from it -- the day's later minutes never choose a stock earlier.
  - **The table** (owner `research/market_reads/signals_store.py`; invalidation: a `builder` bump, or the day's
    relative-volume row rebuilt after the signal day was built, stales that day). Root `NOVA_SIGNALS_DIR`, else
    `F:\Nova\signals` when F: is mounted on Windows, else `<NOVA_MARKET_DATA_DIR>/signals`. `manifest.json`
    `{schema_version: 1, builder, templates: {setup: rev}, rules, days: {YYYY-MM-DD: {rvol_built_ts, stock_days,
    rows, built_ts, seconds, coverage: {board, halts, catalyst_checked, hod_rebuilt, short_interest}}, tape: {YYYY-
    MM-DD: {stock_days, rows, built_ts, seconds}}}}`, each change read, made and replaced under `manifest.lock`
    (one writer at a time across processes); another `schema_version` refuses (`UnknownSignalsSchema`). Parquet, zstd, file metadata `nova_signals` `{schema_version, builder, day, table}`:
    `days/YYYY/YYYY-MM-DD.parquet` one row per stock-day (`date, symbol, kind, prev_close, in_play_m, epoch,
    basis`) and `minutes/YYYY/YYYY-MM-DD.parquet` one row per minute `m` from `in_play_m` through 959 (15:59):
    `date, symbol, m` (int16), `price` (the close of the last bar starting at or before `m`), `change_pct`
    (percent points vs `prev_close`), `rvol, rvol_5m, rvol_daily` (the relative-volume table's three measures at
    `m`), then each signal's columns as the registry names them. The tape stage writes
    `tape/YYYY/YYYY-MM-DD.parquet` (`date, symbol, m, tape, tape_score, tape_flush, tape_burst`) apart; a day it has
    not reached reads `tape` `not_built`.
  - **Signals** (`signal_catalog` lists each with its states, its desk source and its history; states are the
    panel's: `ok`, `warn`, `bad`, `info`, `unknown`; kinds `state`, `label` (one of its values), `text` (a name the
    desk's rule gives, matched exactly: the catalyst category), `number`, `bool`):
    - `in_play` (the tile: `Yes`, `Partly`, `No`, `Too thin`, `Not known`); `pillars` (state) with `pillars_n`
      (0-5) and `pillar_price, pillar_change, pillar_rvol, pillar_catalyst, pillar_float` (bool); `rvol_state`
      with `rvol_pace` (`market.pace_relative_volume` of volume since 04:00 over `day_avg_volume`); `catalyst`
      (the classifier's verdict on items published after the prior session's 16:00 and by `m`: `catalyst`,
      `negative`, `routine_only`, `noise_only`, `none_found`, `not_checked`) with `catalyst_category` (text) and
      `catalyst_strength` (`strong`, `weak`); `why` (`move_reason.rules.read`'s likely kind) with `why_confidence`
      (`likely`, `possible`) and `why_state`; `board` (the
      board `find_board_row` picks at `m` from the leaderboard store: `gappers`, `gainers`, `losers`,
      `afterhours`, `large_cap`, `market`, or null) with `board_state`; `ran_before` (state) with `runs_n` (+40%
      sessions in the prior 260 of the same epoch, from the relative-volume table's `hi` / `last_close` on the
      day's basis); `liquidity` (`ok`, `thin`, `unknown`) with `liquidity_day_usd, liquidity_5m_usd`;
      `hod_today` (state) with `hod_alerts` (a rebuilt HOD Momo day's alerts raised by `m`; null on a day not
      rebuilt).
    - `front` (the tile: `Front side`, `Mixed`, `Back side`, `Not known`) and its counted rows `front_macd_1m,
      front_vwap, front_ema, front_volume_profile, front_hod` (states).
    - `setup_<lane>` for every lane the Trader shows -- `first_pullback, bull_flag, flat_top_breakout,
      flat_top_5m, red_to_green, gap_and_go, pullback_dip, abcd`, the 5-minute `first_pullback_5m, bull_flag_5m`,
      and the short lanes `backside_lower_high, bear_flag, failed_breakout, lost_vwap, ssr_bounce` -- each the
      detector's state at the end of `m`: `watching`, `leg`, `pullback`, `armed`, `near`, `triggered`, `failed`.
      Prices inside a minute are the bar's own: its open one second in, then its high (long lanes) or low (short
      lanes) at 30 seconds -- the order inside a bar is not in the data, so a trigger needs the bar's extreme to
      reach the line.
    - `float` (state) with `float_shares` (SEC shares outstanding filed by the day before, as of within 120 days,
      split-adjusted through the session, a split that day included (`floats.sec_shares` `before`): an upper bound on the float -- under 20M proves the pillar, over it leaves the float
      `unknown`) and `rotation` (volume since 04:00 over it).
    - `halted` (bool, null before Nasdaq's log starts 2021-09-21; a halt carried from the prior exchange day is
      halted until today's log shows its resume), `halts_today` (state) with `halts_n`, and the
      tile `halts` (`Halted`, `No halts`, the count, `Not known`).
    - `tape` (the flow label at the end of `m`: `burst`, `flush`, `neutral`, `quiet`, `blind`, `not_built`) with
      `tape_score`, `tape_flush` and `tape_burst` (any 10-second reading inside the minute so labelled): the desk's
      flow rule over Massive's trades sided against the NBBO in force before each print, the book its top of book.
      `not_built` marks a session the stage has not reached: every answer carries the four tape columns, and a
      condition may not ask for `not_built` (a tape condition reads only the sessions the stage reached).
  - `signal_series {symbol, day, signals?, start?, end?}` -> a table answer, one row per minute of that stock-day
    (`time_et` the minute's start, `in_play_et`), from `start` up to `end` (ET `HH:MM`, end exclusive) when given.
  - `signal_scan {day, at, when?, limit?}` -> every in-play stock-day at `at` (ET `HH:MM`) with its signals, or
    only those meeting `when`.
  - `signal_test {when, filters, window_from?, window_to?, fresh?, up_pct?, down_pct?, horizon?, days?, group_by?,
    control?, seed?, output_name?}` -> `rvol_outcomes`' answer shape (`{ok, entries, summary, control, meta,
    out}`). `when` is a list, all of which must hold at one minute: `{signal, is: state | [states]}` or
    `{signal, min?, max?}` for a number; an unknown signal or state is refused with the registry's words. The
    entry is the first minute `m` in `[window_from, window_to)` (default 04:00-15:59) at or after `in_play_m` where
    every condition holds; `entry_et` is its end and `P` its `price`. `fresh: true` leaves out a stock-day where
    they all held at a minute before the window. Outcomes, horizons and the summary are `rvol_outcomes`' own
    (`_score`, `summarize`). The control: per entry, one in-play stock-day of the same date and filters, in play
    by the entry minute, where the conditions had not all held by then -- seeded hash, scored the same way.
    `group_by`: `year` (default), `hour` or `none`. Only `output_name` writes. `meta.coverage` counts the entries
    whose conditions read a partly covered signal (board, halts, catalyst, HOD Momo, tape) as `unknown`.
- **Tripwire** (`tools/data_access_hook.py`): Cursor `beforeShellExecution` (`{permission: "allow" | "deny",
  user_message, agent_message}`) and Claude `PreToolUse` on Bash (`hookSpecificOutput.permissionDecision: "deny"`).
  Denied: a command naming a raw store (`nova/massive`, `nova/leaderboard`, `catalysts/edgar`, `nova/rvol`, `nova/signals`, `store/reference`,
  the movers / leaderboard / reference-index SQLite files, SEC's zips, the Massive day-file folders) or running a
  script outside the repo that names one. Passes: the front door's tools, repo code, a code search or git not pointed
  at a data folder, and `# raw-data-ok: <reason>`. Unparseable input allows.

## Recorded sessions, Level 2 and tape through the front door (ADR 059, #1064)

Nova's own IBKR recordings, read by the same front door as the Massive files (`research/market_reads/recordings.py`;
CLI `tools/market_data_recordings.py`, MCP `tools/nova_data_recordings.py`). What the Sim replays, research can now
query. **Read-only and invisible to the live desk:** every store is opened for reading only (SQLite
`file:...?mode=ro` with `PRAGMA query_only=ON`, jsonl files opened `rb`); a read never writes a row, creates a store,
changes `journal_mode` or flushes a writer queue. Every database read is a short bounded statement (one row, or at most
`CHUNK_ROWS` = 20,000 in keyset pages, the read transaction ended between statements), so a WAL checkpoint is never held
behind a research read and the desk's writers never wait on it. Opening a WAL database read-only while no writer has it
open leaves SQLite's own empty `-wal` / `-shm` side files beside it (the reader protocol; no content of the store). A
read takes one heavy-read slot (`slots.heavy`). A jsonl stream is searched by byte offset (its rows are in `ts` order:
the recorder refuses a row that moves backwards), never read whole for one moment. Tests run on fixture stores only.

- **Where.** `NOVA_SIM_CAPTURE_DIR` (default `F:\Nova\sim_capture`, the recorder's own `capture.storage.capture_root`):
  `<day>/<SYMBOL>/{manifest.json, prints.jsonl, quotes.jsonl, l2.jsonl}` (a Session Record, "Recording persistence
  and coverage" in `recording-and-replay.md`). The desk cache holds `l2.db` (`l2_snapshots`, `record_sessions`) and
  `archive.db` (`tape_ibkr`, `integrity_counters`): `NOVA_CACHE_DIR` when set (and only that folder), else the main
  checkout's `backend/.cache` (a worktree keeps its own, empty one), this checkout's, then `F:\Nova\cache` (where
  `tools/data_root.py` moves it); the first folder holding the store is read. A store that is not there is a stated
  absence naming every place looked (`LookupError` where there is nothing else to answer).
- **Tools** (`{ok: false, error}` on a failed read, as every front-door tool; all heavy, one at a time per process):
  - `recorded_days {date_from?, date_to?, symbol?, output_name?}` (operator 2026-10-26) -> which days were recorded
    and which stocks each day (`research/market_reads/recorded_days.py`): one row per Session Record folder
    `<day>/<SYMBOL>` under `roots.sim_capture()`, newest day first, then symbol -- `day, symbol, status, first_et,
    last_et, recorded_min, stretches, gaps, unplanned_gaps, problem`. The times come from the manifest's recorded
    segments merged (`recordings.capture_state`, the rule `recorded_depth` / `recorded_tape` read by); `gaps` are the
    stops between them, `unplanned_gaps` those not a planned stop (`CAPTURE_PLANNED_STOPS`). A folder with no
    readable manifest is listed with its `problem`, never dropped; a folder that is not a date or a ticker is not a
    Session Record. Read-only: the root and folders are named, never made (a missing root is a `LookupError`).
    `meta.days` / `meta.symbols` count them; `meta.not_here` says the tape archive (`archive.db` `tape_ibkr`) and
    `l2.db` are not listed -- a whole-table scan -- and `recorded_tape` / `recorded_depth` answer them per stock-day.
    84 Session Records over 5 days read in about 1 s on the operator's F:. CLI `market_data.py recorded-days
    [--from --to --symbol]`.
  - `recorded_depth {symbol, day, at, source?, max_age_sec?}` -> the Level 2 book at ET `at` (`HH:MM[:SS]`):
    `{ok, symbol, day, at, at_et, covered, source, book, reason, tried, coverage, rules, units, recorded_days?}`.
    `source` is `auto` (default: the newest book at or before `at` among the stores, a tie to `capture`) | `capture` |
    `l2_db`. `covered` is true when a book was found and `source` names the store that served it; when false,
    `book` and `source` are null and `reason` says why per store. `book` is `{ts, time_et, age_sec, bids: [{price,
    size}], asks: [{price, size}], best_bid, best_ask, spread, mid, bid_levels, ask_levels, source, setup?,
    session_id?}` -- each side best price first, `age_sec` the seconds between the book and `at`. `tried` is one
    `{source, covered, reason, book_ts, book_et, age_sec}` per store asked, so a book the other store held is
    visible. `max_age_sec` (default 60, above 0 and at most 3,600) is how far before `at` a book still counts.
  - `recorded_tape {symbol, day, start?, end?, source?, limit?, output_name?}` -> a table answer (rows `time_et, ts,
    receive_ts, exchange_ts, price, size, exchange, conditions, unreported, sets_price, side, bid, ask, source`) of
    the prints in ET `[start, end)` (default the whole ET calendar day), oldest first. `source` is `auto` (default:
    `capture` when a usable Session Record with prints exists for the symbol-day, else `archive`) | `capture` |
    `archive`. `limit` (default 200,000, at most 1,000,000) caps the rows; `meta.capped` says more matched.
    `output_name` writes a new file like the other table tools. `meta` carries `source` (served), `window_et`,
    `where` (the folder read), `coverage`, `rules`, `units`, `note` (a stated absence or a pointer to the other
    store) and, when no row matched, `recorded_days`.
- **Times are ET and are Nova's clock.** `at`, `start` and `end` are ET wall times `HH:MM[:SS[.fff]]` read on the
  asked day's own clock (a day the clocks change reads right: 03:30 on the spring change is 03:30 EDT); `24:00`, and only
  that, is the end of the day. `time_et` is `HH:MM:SS.mmm` of `ts` and every `*_et` in `coverage` is ISO
  with the ET offset. `ts` is epoch seconds when Nova **received** the print (ib_async stamps arrival;
  `ibkr/tape_events.py`), `receive_ts` when the desk processed it (a Session Record and the archive keep both).
  `exchange_ts` is IBKR's own whole second when the tick carried one (Session Records only; null in `archive`, which
  does not store it). A book's `ts` is when Nova received that book. The "day" is the ET calendar day of `ts`, the
  folder the recorder files it under (a DST day is 23 or 25 hours).
- **Prints.** `side` (`ask` | `bid` | `between` | `unknown`) is the desk's own judgement against the book it held at
  receipt (`ibkr/tape_side.py`: `unknown` when no usable book was held, a missing, crossed or locked one), `bid` / `ask`
  the top of book it was judged against (null then); `side` is null only on a row recorded before the field existed.
  Never inferred from price (PFAI 2026-10-13 08:22:30-08:26:30: 24,257 `between`, 8,160 `ask`, 6,103 `bid`, 614 `unknown`). `sets_price` is the recorded verdict in a Session Record and
  `sale_conditions.sets_price(conditions)` in `archive` (which does not store IBKR's `unreported` flag, so an
  unreported print with ordinary conditions reads true there; `unreported` is null in `archive`).
- **The sources.** `capture`: a Session Record, only for symbols someone recorded (the operator, or auto-record; at
  most 3 at once), 2026-09-19 on, books kept at most 50 a second (`l2_max_hz`). `l2_db`: Level 2 snapshots the desk
  sampled while a depth session was open (`record_sessions`: signal windows and about one a second); an `l1_fallback`
  row is top of book only, never a ladder, and is skipped. `archive`: every print the desk's tape line saw for any
  symbol, 2026-07-15 on; `l2.db` `tape_trades` holds the same prints for watched symbols (`ibkr/tape_recording.py`
  fans each print to both) and is not read separately.
- **What a recording does not cover** -- `coverage`, per store asked, never left out:
  - `capture`: a Session Record whose manifest names a `schema_version` / `schema` the recorder does not know is
    refused, as `capture.schema.read_manifest` refuses it (`covered: false` / an empty table, `reason` / `note`
    `Unsupported capture schema ...`); otherwise `{recorded, status, stretches: [{start_et, stop_et, status, reason}], gaps: [{start_et, stop_et,
    reason, planned}], fidelity: {l2_offered, l2_coalesced, l2_max_hz, tape_resubscribes, timestamp_regressions,
    tape_losses: [{at_et, cause}]}}` (the manifest's own segments, an open one ending at its last write on disk) and,
    for depth, `at_in_stretch` (true / false / null when the manifest names no segment). `l2_offered - l2_coalesced`
    is what the recording kept of the books IBKR sent. A read at a moment no stretch holds answers nothing, and a
    read never reaches back across a gap (`planned`: the gap followed an operator or auto-record stop; a restart or
    failure is not planned). A quiet stretch inside a segment is not a gap. For tape, `covered_share` is the
    fraction of the window inside a stretch.
  - `l2_db`: `{first_ts, first_et, last_ts, last_et, sessions: [{session_id, reason, setup, started_et, ended_et}],
    sessions_truncated, where}` for the symbol-day: outside `first`..`last` and between sessions nothing was
    sampled. `sessions` holds at most 50 (oldest first); `sessions_truncated` is true when more overlapped the day
    (a busy name has many short signal windows), and the served book's own session is always listed.
  - `archive`: `{first_ts, first_et, last_ts, last_et, dropped_total, gaps}` -- the window's first and last print,
    `dropped_total` (lifetime prints the writer shed under load: counted, not stamped by time) and `gaps`, text saying
    the archive is a write log that marks no gap of its own (a quiet stretch and a lost tape line look alike; a
    Session Record of the symbol-day states its gaps, and `auto` points to the archive when the record has them).
  An unrecorded symbol-day is `covered: false` (depth) or an empty table (tape) with `reason` / `note` and
  `recorded_days`: `{source: [YYYY-MM-DD, ...]}`, the newest days that symbol is recorded in each store (at most 30).
- **Not here:** the book watcher's marks (`F:\Nova\book_watch`) and the Session Records' quotes (`quotes.jsonl`), both
  recorded and not served yet (#1103), any symbol nobody recorded or watched, and any moment outside the stretches
  and sessions above.

## Desk review charts (unified MCP)

The same MCP process (`tools/nova_mcp.py`) serves the 32 data tools and one chart tool, `nova_chart`.
`docs/nova-mcp.md` is the setup. `/review` mounts the desk `ChartGrid` and `TickerChart` through a recorded
feed (`ChartFeedProvider` in `frontend/src/chart/chartFeed.tsx`). The live desk is unchanged: with no provider
the feed is `{kind: "live"}` and the same hooks run. The review page does not mount the trading shell, does not
subscribe to a quote, and has no order ticket. `nova_historical_chart`, `nova_historical_chart_gallery` and
`nova_trade_charts` are not on this server. Marked sub-minute candle-gateway PNGs stay on `tools/nova_chart_mcp.py`.

- **Feed seam.** `ChartFeed` is `{kind: "live"}` or `{kind: "recorded", symbol, date, asOfIso, source, bars, vwapBars, notes?}`.
  `bars` holds `10Sec`, `1Min`, `5Min`, `1Day`. `TickerChart` picks `LivePane` or `RecordedPane` as two components.
  The live pane is a dynamic import, so `/review` does not load it, the bots page chunk, or the bot allowlist.
  The recorded pane paints the given bars once, builds VWAP from `vwapBars`, and keeps drawings in memory
  (`useEphemeralDrawings`). It does not call `useChartBars`, the ticker stream, the drawing store, the countdown,
  or the order menu. `useIbkrStatus` does not poll under a recorded feed. `ChartGrid` and the recorded grid share
  `ChartGridFrame`. The live grid warms bars and clears the saved drawing store. The recorded grid skips
  `ensureBarsBatch` and clears the ephemeral drawings on Clear all. `panels` still defaults to
  `buildChartGridPanels()`. Review levels (HOD, LOD, premarket high, opening range, prior high, low and close, flat
  tops) go through the existing `renderPaneOverlay` slot.
- **Page.** `GET /review?symbol=IMCC&date=2026-09-18&tf=1m,5m,10s,1d&as_of=16:00` draws four panes in desk order:
  5-minute, 10-second, full day, 1-minute. `as_of` is `HH:MM` ET and defaults to `16:00` (session 04:00 to 16:00).
  `symbols=A,B,C` (1 to 9) is a gallery with tabs `10s`, `1m`, `5m`, `1d`. The selected tab is `gtf` (default `5m`).
  The header names that timeframe. Each cell is the desk `TickerChart` for that pane and links to the four-pane page.
  Switching tabs repaints the loaded payload. `fixture=1` dynamic-imports the sample module and draws a labelled
  sample. That module is not in the production bundle otherwise, and the sample does not call the API.
  `api` is accepted only for `http://127.0.0.1` or `http://localhost` (optional port). `data-review-ready="1"` is set
  after every visible pane has painted.
- **Engine.** One detached process (`tools/nova_review_engine.py`) owns the loopback listener and the one Chromium.
  The first `nova_chart` call starts it. Later MCP processes attach. Health is
  `{ok, service: "nova-review", version, renderer_starts, pid, build}`. The version is `"3"`. A mismatch restarts the engine.
  `build` is the last build check, `{state, source, build?, built_at?, fingerprint?, detail?}`: `state` is `unchecked`,
  `fresh`, `stale` (an older build is served because building failed), `unavailable` or `override`; `source` is
  `dist-review`, `frontend/dist`, `none` or `NOVA_REVIEW_DIST`. The field is additive, so the version stays `"3"`.
  It exits after 30 minutes idle. Default port is 18765 (`NOVA_REVIEW_PORT`), never 8765. Before it binds, a port
  whose review health check already answers as this engine is left alone. On Windows the socket sets `SO_EXCLUSIVEADDRUSE`
  so a second process cannot share the port. A taken port binds a free one and the link carries loopback `api=`
  when the link origin is not the engine. The engine serves its own build at `/review` and `/assets/` (`tools/nova_review_build.py`): `frontend/dist-review/<id>/`,
  named in `frontend/dist-review/current.json` `{schema_version: 1, build, fingerprint, built_at, previous}` (owner
  `nova_review_build.py`; invalidated when the frontend source fingerprint changes, then rebuilt with the checkout's Vite;
  another `schema_version` is ignored and rebuilt). The current build is asked first, then `previous`; `frontend/dist`
  is served only when no build can be made and its bundle holds the review page; `NOVA_REVIEW_DIST` overrides all of
  it and never builds. Before `/review` and before a screenshot the engine checks the source (at most every 30 s while
  fresh; a failed build is retried after 5 minutes). With nothing to serve, `/review` is HTTP 503 and the chart call's
  code is `REVIEW_BUILD_UNAVAILABLE`. A static
  path is `os.path.realpath`'d and must start with the folder being served before the file is opened. `..` and `%2e%2e` are HTTP 404. `NOVA_REVIEW_BASE`, when set,
  is the link origin. When it is unset, links use the engine's own origin, because that process serves `/review`.
  `--review-http` / `NOVA_REVIEW_HTTP=1` starts the engine at process start. `--no-review-http` does not listen.
- **Data.** `GET /api/review` answer: `{ok, schema_version: 1, symbol, date, as_of, as_of_iso, source, lookahead: false,
  vwap_anchor: "04:00", timeframes: {1m|5m|10s|1d: {bars: [{t, o, h, l, c, v}], source?}}, levels, setups, vwap}`.
  `source` names where a frame's bars came from: the front door's are `massive-trades` (10s, built from Massive's
  consolidated trades by `reads.bars`), `massive-minutes` (1m, 5m) and `massive-daily` (1d; the session's own candle
  is summed from its minutes). A reader that names no source (a test, any other reader) sends none (additive;
  `schema_version` stays 1). Each pane's subtitle is that source (`10s · Massive tape -- built from the consolidated
  trades`; the fixture's is `Sample -- not a recorded day`), through the recorded feed's `notes`; a pane with no
  source says none. The live desk's pane notes (IBKR history, the live tape) never show on a recorded feed. Intraday `t`
  is an ISO instant with an Eastern offset. Daily `t` is `YYYY-MM-DD`. Volume-only buckets and a daily row with
  non-finite OHLC are dropped, so the JSON has no `NaN` (`allow_nan` false). A bad query is HTTP 400 `{ok: false, error}`.
  An unknown path is 404. A reader failure is 500. Success is 200. The engine passes the front-door bar readers
  into that route. CORS allows the configured desk origin and the engine's own origin.
- **Causal.** A bar is included only when its window has ended by `as_of` (a 09:55 5-minute bar waits until 10:00).
  The client drops any later bar again before paint. HOD, LOD and premarket high come from the kept 04:00 to 16:00
  minutes. Opening-range high and low stay null until 09:35. Prior high, low and close are the last finite daily row
  strictly before the session. The session day's daily candle is the aggregate of those minutes (the official daily
  row for that day, and any later day, is not used). VWAP is the desk's session VWAP from 04:00. Setups are flat tops
  of three closed 5-minute bars. `daily_bars` lookback is 183 calendar days. No IBKR call.
- **`nova_chart`.** Arguments, and no others (`additionalProperties: false`): `symbols` (1 to 9 tickers, required),
  `date` (`YYYY-MM-DD`, required), `as_of` (`HH:MM` ET, optional, default `16:00`). Any other argument is an MCP error
  whose text starts with `UNKNOWN_ARGUMENT` and names it. Fixed in code: timeframes `10s`, `1m`, `5m`, `1d`; full
  session; desk overlays at the desk defaults (EMAs 9/20/200, VWAP from 04:00, MACD on 1m and 5m, session shading,
  volume, review levels). Annotations: `readOnlyHint` false, `idempotentHint` false, `destructiveHint` false,
  `openWorldHint` false. Content order: one text block that is exactly `chat_message`, then PNG image blocks (one per
  symbol, plus one gallery PNG of the 5m tab when there is more than one symbol), then `structuredContent`
  `{ok, chat_message, date, as_of, timeframes, links: [{symbol, url}], gallery_url, images: [{symbol, sha256, bytes}]}`.
  On failure `ok` is false, `error` is `{code, detail}`, and `chat_message` still lists any links that were built.
  `REVIEW_DESK_UNREACHABLE` means the review page could not be screenshotted. `REVIEW_SHOT_UNAVAILABLE`
  means `--no-warm-shots`. `REVIEW_BUILD_UNAVAILABLE` means no build of the review page exists or can be made. A clock that is not ASCII `HH:MM` is `BAD_REQUEST` and still returns an ASCII
  `chat_message`. Links are built by `review_link` and `gallery_link` in `tools/nova_review_causal.py`.
- **Shot.** `POST /api/review/shot` accepts `Content-Type: application/json` and header `X-Nova-Review-Token`.
  The token is random per engine and stored in the lease file next to `port` and `pid` (`schema_version` stays 1).
  A missing or wrong token is 401. Any `Origin` header is 403. A content type other than `application/json` is 415.
  A body that is not a JSON object is 400. The body may carry
  `symbol` or `symbols`, `date`, `as_of`, and `gtf`. A `url` or `dest` field is 400. The engine builds the page URL
  on its own origin from those fields and chooses the PNG name inside its review-shots folder. That path is
  `os.path.realpath`'d and must stay inside the folder, and the folder must sit under the system temp directory,
  before a PNG is written or deleted. Rotation of old PNGs runs under the same lock as the shot and does not delete
  a file another request is about to return. An `Origin` value is stripped of CR and LF before it can be echoed.
- **`chat_message`.** ASCII. Line 1: `Nova charts for {date}, as of {as_of} ET (10s, 1m, 5m, 1d, full session):`.
  Then one line per symbol: `- {SYMBOL}: {url}`. Then, only for more than one symbol, `Gallery: {gallery_url}`.
  Then, only when a PNG failed, `Preview images unavailable: {code}`. An MCP prompt `chart_request` tells the model
  to call `nova_chart` and post that text verbatim. The tool enforces the shape without the prompt.
- **Drawings** on `/review` stay in the page's memory. They are not written to the operator's drawing store.


