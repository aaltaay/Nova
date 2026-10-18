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
