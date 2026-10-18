# Historical OHLCV charts through Nova

Use Nova's existing candle, volume and native snapshot renderer for historical
OHLCV charts. The offline gateway reads explicit local inputs; it does not search
for instruments, fetch data or operate the trading desk.

## Export a symbol and day

From the selected Nova checkout, replace the placeholders with an exact symbol,
ISO date, existing minute-Parquet root, reviewed gateway checkout and new output:

~~~powershell
py -3 tools/nova_historical_charts.py export --symbol SYMBOL --date YYYY-MM-DD --massive-root "<MINUTE_ROOT>" [--fallback-massive-root "<MASSIVE_ROOT>"] --gateway-root "<NOVA_CHECKOUT>" --output "<NEW_OUTPUT>" [--as-of-m 585] [--annotations-json '[{"kind":"horizontal_line","price":10.5,"label":"Entry","color":"green"}]'] --samples 0
~~~

The input is resolved from `<MINUTE_ROOT>/d=YYYY-MM-DD/part.parquet` (columns
`ticker,m,o,h,l,c,v`) or Massive's `<ROOT>/minute_aggs_v1/YYYY/MM/YYYY-MM-DD.csv.gz`
(with optional `--fallback-massive-root` so no date gap occurs across the archive).
The resolver selects the exact ticker; `m` denotes an America/New_York minute start,
in raw same-session price/share units. For multi-entry galleries (`1..9` symbol-days
in one pass), pass `--entries-json '[{"symbol":"DEMO","date":"2022-02-01"}]'`.
There is no remote download, reference-universe filter, broker-history or simulation fallback.

The resolver freezes hashed OHLCV projections and delegates to the shared export
lifecycle. Its owning contract is
[local-historical-charts.md](../architecture/schema/local-historical-charts.md).
Keep source data, projections, images and runtime receipts outside the source tree.

## Export an existing frozen selection

~~~powershell
py -3 tools/nova_charts.py export --selection "<SELECTION_JSON>" --sha256 "<RECORDED_SHA256>" --output "<NEW_OUTPUT>" --samples 0
~~~

The selection has schema_version:1, kind:"historical_ohlcv", a family label and
1..9 selected entries. Each entry supplies day, ticker, optional as_of_m,
annotations and bar_projection:{path,sha256}. Identities (day,ticker,as_of_m) are
unique and ordered; repeated tickers on different dates/boundaries are allowed.
The exact wire and validation rules live in
[agent-desk.md](../architecture/schema/agent-desk.md#historical-ohlcv-chart-gateway-operator-2026-10-18).

Each projection is an absolute path in the selection's sibling bars/ directory.
It declares matching day/ticker, time_zone:"America/New_York",
m_semantics:"minute_START", price_units:"raw_same_session_YYYY-MM-DD",
observed_source_start_m, observed_source_end_exclusive_m, and bars:[{m,o,h,l,c,v}].
Hashes bind exact bytes. Preserve actual units and gaps; do not invent observations.

Without as_of_m, Nova displays the full observed session. With an integer boundary
0..1440, whole later/crossing candles are shaded amber. Missing boundary candles
do not postpone that mask. Only five actual consecutive observed minutes form a
wall-clock 5m candle.

annotations contains at most 32 objects. Supported kinds are horizontal_line
(price,label,color?) and time_marker (minute,label,color?). Labels are 1..80 text
characters; price is positive/finite; minute is an integer 0..1439. Optional color
is blue, gold, grey, green or red (default blue). Unknown kinds/fields and arbitrary
CSS are refused. These are caller-provided presentation marks, not inferred signals.

## Receipts, isolation and timing

Use a new output directory. Existing output/source files are preserved.
EXPORT_RECEIPT.json reports PNG paths/hashes, phase timings and cleanup status;
phase logs and partial output remain on failure. Check success and owned-child
cleanup before reporting completion.

The command owns isolated read-only data, chart-only frontend and browser children
on two available loopback ports. On Windows, an owned Job includes descendants
before real commands launch and cleanup verifies zero active owned processes.
Per-run instance checks reject unrelated listeners; readiness ignores inherited
proxies and rejects redirects. The chart-only frontend loads no environment files.
No trading-app lifespan, live bars, subscriptions, account changes or orders run.
Unsupported platforms fail before service launch until equivalent cleanup is tested.

Default --samples 0 performs one export without repeated timing loops.
When benchmarking, report n and p50/p95 separately for source loading, aggregation,
first/warm fetch/paint, native capture/PNG composition, browser startup and transport.
Subsecond initialized rendering is a target; it is not a cold-start or full-command guarantee.

For an already-loaded chart, use Nova's existing Snapshot action described in
[agent-operations.md](agent-operations.md). Do not create another candle renderer.

## Optional MCP access

The optional tools/nova_chart_mcp.py server exposes the same generic historical
chart capability. Follow [the MCP setup guide](NOVA_CHART_MCP.md) for the scoped
SDK/environment and explicit local-root configuration. Server availability does
not install a client connection or grant
permissions. Client configuration and per-action authorization remain separate;
no global grants, automatic data discovery or trading access are implied.
