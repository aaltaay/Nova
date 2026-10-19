# Local historical chart bundles

The tools in `tools/nova_historical_charts.py` and `tools/nova_historical_resolver.py`
own one offline ticker/day export. They read the operator's explicit local minute
root, never the trading backend, a subscription, an account, a remote URL, or an
environment-selected data path. SOP: validate request and local paths, project the
exact ticker from one day file, verify source integrity, freeze a new bundle, then
call Nova's existing offline chart exporter in an explicitly approved checkout.

The supported input layouts under the approved minute root (and optional
`--fallback-massive-root`) are:

1. `<root>/d=YYYY-MM-DD/part.parquet` (or `<root>/minute/d=YYYY-MM-DD/part.parquet`),
   with columns `ticker, m, o, h, l, c, v`.
2. `<root>/minute_aggs_v1/YYYY/MM/YYYY-MM-DD.csv.gz` (or
   `<root>/YYYY/MM/YYYY-MM-DD.csv.gz`), Massive's official minute flat-file layout
   (`ticker,volume,open,close,high,low,window_start,transactions`), where
   `window_start` UTC nanoseconds convert to integer ET minute starts `0..1439` on
   `YYYY-MM-DD`.

`m` is an integer minute start in ET, from 0 through 1439. Prices are raw on that
same session's share basis; volume is shares. When the primary root lacks a day
partition and `--fallback-massive-root` is configured, the resolver reads the fallback
root so no date gap occurs between derived Parquet partitions and the full Massive
archive. The resolver uses the existing optional DuckDB research reader with
`allowed_paths` locked to the single resolved file and `enable_external_access = false`;
it never installs dependencies. Missing file, absent exact ticker, malformed rows,
unsupported schema, unsafe path, and changed input are distinct failures.

The frozen `selection.json` is:

```json
{"schema_version":1,"kind":"historical_ohlcv","family":"historical-chart",
 "selected":[{"day":"2022-02-01","ticker":"DEMO","as_of_m":585,
 "bar_projection":{"path":"<absolute-new-output>/bars/01.json","sha256":"<hash>"},
 "annotations":[{"kind":"horizontal_line","price":10.5,"label":"Entry","color":"green"}]}]}
```

`as_of_m` is omitted when not requested (`0..1440` integer minute boundary when set).
`annotations` defaults to `[]` and accepts `0..32` validated `horizontal_line` or
`time_marker` objects. Multi-entry gallery bundles (`1..9` entries via
`resolve_gallery_bundle` or `--entries-json`) write `bars/01.json` through `bars/09.json`
ordered uniquely by `(day, ticker, as_of_m)`.

The projection contains exactly `day`, `ticker`,
`time_zone: "America/New_York"`, `m_semantics: "minute_START"`,
`price_units: "raw_same_session_<day>"`, `observed_source_start_m: 0`,
`observed_source_end_exclusive_m: 1440`, and `bars: [{m,o,h,l,c,v}]`.
Source provenance (local file SHA256, size, timestamp, selected columns and exact
ticker) lives separately in `provenance.json` and the returned bundle receipt.
Rows are chronological and unique. Null, non-finite, negative-volume, nonpositive
price, invalid-envelope and duplicate-minute rows fail closed. Empty minutes
remain absent; there is no filling, gap bridging, cross-day adjustment or invented
volume. The native exporter forms five-minute bars only from five consecutive
observed wall-clock minutes.

There is no decision time, pattern, guard, trade, signal, stop, target or performance
claim in a generic bundle. Optional future annotations belong to the native
exporter schema, not this resolver's interpretation of the data.

An output folder must not exist. Its parent must exist and be local. Input/output
paths reject traversal components, symlinks, junction/reparse paths and network
roots. The fixed children `bars/01.json`, `selection.json`, `provenance.json` and
`images/` stay in that newly claimed folder. Bundles and images remain local
operator data; only generic source and generated fixtures belong in public Git.

CLI: `python tools/nova_historical_charts.py export --symbol DEMO --date 2022-02-01
--output <new-folder> --massive-root <local-minute-root> --gateway-root
<approved-Nova-checkout> --samples 0`. This claims a new bundle and delegates PNG
capture to `tools/nova_charts.py export`; it does not start the trading application.
Loading/freezing, native export, and total elapsed time are reported separately.
The standalone native-export subprocess has a 180-second timeout. Failure preserves
the frozen bundle and existing native phase logs; a timeout also saves captured
stdout/stderr in `native_export_failure.json` and never creates a success receipt.

## Trade charts (trade list in, marked charts out)

`tools/nova_trade_charts.py` owns turning a caller's trade list into one frozen gallery of
sub-minute charts with the fills marked, then delegates PNG capture to the same native
exporter (`run_native_export` in `nova_historical_charts.py`). MCP: `nova_trade_charts`.

```text
py -3 tools/nova_trade_charts.py export --trades-file trades.json --output <NEW> --massive-root E:\Nova\massive [--bar-seconds 10] [--before 300] [--after 120] [--family "..."] [--warm [--idle-seconds 600]]
```

`--warm` draws through the warm renderer (`tools/nova_chart_warm.py`, "Warm renderer" in
[agent-desk.md](agent-desk.md)), starting one when none is running for the gateway
checkout; without it the one-shot export runs as before. `historical_export.json`
records which (`native_export.renderer`). The MCP tool always draws warm, through a
renderer the MCP server owns ("The MCP server's warm renderer" in agent-desk.md).

A trade is `{symbol, date, entry_time, entry_price, exit_time, exit_price}` or, for
partial exits, `{symbol, date, entry_time, entry_price, exits:[{time, price}, ...]}`
(1..8 exits), with optional `stop`, `pivot` (positive prices, drawn as grey / gold
`horizontal_line`s) and `label` (1..40 printable characters, shown on the buy arrow).
Times are ET `HH:MM:SS` with optional fractional seconds; an exit before its entry,
unknown fields, or a non-positive price is `invalid_trade`.

- Trades on the same symbol and date share one chart (one gallery entry); 1..9
  stock-days per call, at most 32 marks per stock-day.
- Each stock-day's window runs `before` seconds before its first entry to `after`
  seconds after its last exit, snapped outward to the bar grid; bars are 1, 5, 10, 15
  or 30 seconds (default 10).
- Bars come from that day's Massive `trades_v1` file under the explicit
  `--massive-root` through the market data front door (`market_reads.bars`, the Sim's
  rule: a cancel/error record is no trade, price-setting prints set OHLC, every trade
  counts in volume). The reader is asked for the window's whole minutes only
  (`read_span_s` in provenance, seconds after midnight ET, end exclusive), and the
  front door parses only those minutes' lines ("Read cache" and "Windowed reads" in
  [agent-desk.md](agent-desk.md)). A bucket with volume but no price-setting print stays a gap and is
  counted in provenance (`volume_only_buckets_left_as_gaps`). A stock-day with no
  priced bar in its window is `symbol_missing`; a root without `trades_v1` is
  `trades_root_missing`; a missing day file is `day_missing`.
- Reads run in parallel threads before the output folder is claimed, in the export's own
  short-lived process (never in the warm renderer: long-lived readers of many day files
  lose their seek index, #983). The day file is multi-GB, so provenance records its path,
  size and modification time (checked before and after the read), not a SHA256; the
  frozen projection files are SHA256-bound as for minute bundles.
- Bar cache (`tools/nova_trade_bar_cache.py`, its only reader and writer): each stock-day
  read keeps the bars it read at the requested size in
  `<cache_dir>/trade-chart-bars/<date>/<SYMBOL>_<n>s.json` (`paths.cache_dir()`:
  `NOVA_CACHE_DIR` or `backend/.cache`) as
  `{schema_version:2, symbol, day, bar_seconds, span_s:[start,end], source:{path,size,mtime_ns},
  reader_sha256, bars:[[s,o,h,l,c,v], ...]}`, prices `null` for a volume-only bucket. A later
  chart of that stock-day uses it only when its read span lies inside `span_s` and the day
  file's path, size and modification time and the hash of the reader's code
  (`market_reads/reads.py`, `sim/massive_files.py`, `constants_sim.py`) all still match;
  anything else (another span, an unknown `schema_version`, or an unreadable file) is a
  miss that reads that span and rewrites the entry. A `schema_version:1` entry held the
  whole session and is read as `span_s:[0,86400]`. At most 2000 entries are kept (oldest removed). Provenance says
  `cache: "hit"` or `"miss"` per stock-day; a hit's bars are the same rows the reader
  returned, so the drawn chart is the same.
- Each fill becomes a `trade_marker` (buy arrow green, sell arrow red). Fills are the
  caller's marks; nothing is inferred, filled or adjusted.

Output: the usual bundle (`bars/NN.json` sub-minute projections, `selection.json`,
`provenance.json` with `read_ms`, `images/`) plus `historical_export.json`; detail PNGs
are `images/images/NN_<TICKER>_<date>_<n>s.png`.
