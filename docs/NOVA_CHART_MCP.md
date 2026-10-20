# Historical charts for agent clients

The desk-looking charts (interactive `/review` links and PNGs of that page) are `tools/nova_mcp.py`.
See `docs/nova-mcp.md`. This page is the older candle-gateway exporter (`tools/nova_chart_mcp.py`).

Nova offers two optional MCP tools, `nova_historical_chart` (single symbol/day)
and `nova_historical_chart_gallery` (`1..9` symbol/day entries in one pass).
Both delegate to `nova_historical_charts.py export` and the existing isolated Nova
renderer. They return verified PNG paths, SHA256 hashes, a receipt and
zero-active-process cleanup status. The successful MCP response also carries one
inline PNG (the paired 1m/5m chart for `nova_historical_chart`, or the 3x3 overview
chart for `nova_historical_chart_gallery`) so clients can inspect it without
filesystem access. No Sim selection or running
trading desk is required. See `architecture/schema/agent-desk.md` and the local
historical resolver schema for the contracts.

`nova_historical_chart` accepts:

```json
{"symbol":"DEMO","date":"2020-01-02","output_name":"demo-chart-01","samples":0,"as_of_m":585,"annotations":[{"kind":"horizontal_line","price":10.5,"label":"Entry","color":"green"}]}
```

`as_of_m` (`0..1440` integer minute boundary) and `annotations` (`0..32`
`horizontal_line` or `time_marker` objects) are optional.
`nova_historical_chart_gallery` accepts `entries` (`1..9` items with `symbol`,
`date`, and optional `as_of_m` and `annotations`), `output_name`, optional `family`,
and `samples`.

`nova_trade_charts` takes `trades` (the list described under "Trade charts" in
`architecture/schema/local-historical-charts.md`, at most 50 trades on 1..9
stock-days), `output_name`, optional `bar_seconds` (1, 5, 10, 15 or 30; default 10),
`before_s` / `after_s` (window seconds, default 300 / 120), `family` and `samples`.
It reads Massive trades from the `--fallback-massive-root` (else `--massive-root`),
which must hold `trades_v1` (`TRADES_ROOT_MISSING` otherwise), and returns one
`NN_<TICKER>_<date>_<n>s.png` per stock-day plus the overview.

`symbol` is an exact case-preserved resolver token (1..32 ASCII letters/digits or
the supported punctuation `. ^ _ -`; first character is alphanumeric). `date` is
a valid `YYYY-MM-DD`. `output_name` is one new directory name, at most 64 ASCII
letters/digits/underscore/hyphen, starting with a letter or digit; Windows device
names are refused. `samples` is a strict integer 0..50; booleans are refused.
Default0 performs no benchmark loop. The requested day must be present in the
host-approved local minute root (or optional `--fallback-massive-root`) using the
resolver's confirmed partition or Massive `.csv.gz` schema.
The tool does not download or discover a remote dataset.

Always check `ok` before using artifacts. A tool invocation can return
`{"ok":false,"error":{"code":"OUTPUT_ALREADY_EXISTS"}}` or another fixed error
code. SDK argument/schema errors use MCP's error result. Existing output is
preserved. Failed native output remains available for local diagnosis; raw child
logs/provider exceptions never become tool error text. The response omits raw
input paths and provenance; the authorized output directory retains full receipts.
The inline PNG is capped at 2MiB and rechecked against its verified path, PNG
signature, size and SHA256 immediately before encoding. Missing, ambiguous,
oversized or changed detail content produces an MCP error with no image; the
earlier verified metadata remains under `verified_export`. No caller can request
an arbitrary image path or filesystem resource. Other native artifacts and their
receipts remain available through the returned structured metadata.

## Install the optional SDK in an approved environment

Use an explicitly approved project virtual environment and the separately pinned
`tools/requirements-chart-mcp.txt` (`mcp==1.26.0`). Nothing installs automatically,
including when a client starts the server. The official SDK implements discovery,
validation and stdio transport; Nova does not implement JSON-RPC itself. The
matching [official SDK source](https://github.com/modelcontextprotocol/python-sdk/tree/v1.26.0)
and [package metadata](https://pypi.org/project/mcp/1.26.0/) identify this version.

The SDK environment and existing export environment can differ: pass a trusted
`--export-python` runtime that already has the local reader and native export
dependencies. Without it, the SDK interpreter is also used for export. Do not
install the full trading app to make an MCP client work.
Only this omitted default is canonicalized on non-Windows hosts, accommodating
the already-running interpreter's symlink. Explicit `--export-python` paths keep
strict checks; Windows behavior and all data/output root restrictions are unchanged.
POSIX process-tree ownership remains unsupported.

Launch using absolute, operator-approved replacements for these placeholders:

```text
SDK_PYTHON -B NOVA_CHECKOUT/tools/nova_chart_mcp.py --resolver-root RESOLVER_CHECKOUT --gateway-root GATEWAY_CHECKOUT --massive-root LOCAL_MINUTE_ROOT --output-root DEDICATED_OUTPUT_ROOT --export-python EXPORT_PYTHON
```

After source integration, the resolver and gateway checkouts may be the same
approved Nova checkout. During development, explicit separate checkouts work
without copying a renderer. All roots must already exist, be dedicated local
directories, and contain no symlink/junction/reparse components or network drive.
The output root must not overlap the source/data roots. The server never creates
or expands those grants. It permits one export at a time, with a 240-second total
budget; the resolver/native exporter has its own shorter limits. Cancellation,
timeout or unverified owned-process cleanup cannot return success. Windows Job
Objects contain descendants before real commands launch; other platforms fail
clearly until equivalent cleanup is supported.

The MCP server uses stdio only. The existing native renderer starts its own
temporary loopback services. No authentication listener, persistent daemon,
environment-file lookup, arbitrary resource/file reader, broker route, live
subscription or desk command is exposed. The SDK constructor runs in a new empty
temporary working directory so its default `.env` lookup cannot read a checkout's
private environment. The original directory is restored before serving requests.

## Review client configuration before enabling access

These are templates, not installed settings. Approve each client, executable,
data root, output root and chart capability first. Merge only the reviewed server
entry into an existing configuration; preserve all unrelated entries and secrets.
Do not replace the whole file or put access tokens in these templates.

For Codex, use the user or trusted project configuration described in the
[official MCP documentation](https://developers.openai.com/codex/mcp/):

```toml
[mcp_servers.nova_charts]
command = "SDK_PYTHON"
args = ["-B", "NOVA_CHECKOUT/tools/nova_chart_mcp.py", "--resolver-root", "RESOLVER_CHECKOUT", "--gateway-root", "GATEWAY_CHECKOUT", "--massive-root", "LOCAL_MINUTE_ROOT", "--output-root", "DEDICATED_OUTPUT_ROOT", "--export-python", "EXPORT_PYTHON"]
enabled_tools = ["nova_historical_chart"]
default_tools_approval_mode = "prompt"
startup_timeout_sec = 20
tool_timeout_sec = 260
```

For Cursor, add a reviewed entry using its
[MCP configuration format](https://cursor.com/docs/mcp):

```json
{"mcpServers":{"nova_charts":{"type":"stdio","command":"SDK_PYTHON","args":["-B","NOVA_CHECKOUT/tools/nova_chart_mcp.py","--resolver-root","RESOLVER_CHECKOUT","--gateway-root","GATEWAY_CHECKOUT","--massive-root","LOCAL_MINUTE_ROOT","--output-root","DEDICATED_OUTPUT_ROOT","--export-python","EXPORT_PYTHON"]}}}
```

Claude Desktop uses the same `mcpServers` entry without Cursor's `type` field;
follow the [official local-server configuration guide](https://modelcontextprotocol.io/docs/develop/connect-local-servers).
Client approval policy remains operator-controlled. No template auto-approves tool
calls or grants the trading application. Clients may need restart/reload after a
separately approved configuration change.

## Verification

Run generated boundary and installed-SDK tests:

```text
SDK_PYTHON -B -m unittest discover -s tools -p test_nova_chart_mcp.py -v
```

For the opt-in real SDK stdio test, set `NOVA_TEST_GATEWAY_ROOT` to the explicitly
approved gateway checkout. The test generates its own resolver and PNG fixture;
it checks initialize/list/call/error behavior and real Windows ownership without
reading market inputs. A fixture transport pass is not proof of native rendering.
Test the full local resolver/native renderer separately with a generated minute
partition, record hashes and cleanup, and inspect the images before claiming that
end-to-end path. A one-second warmed-renderer goal does not imply a one-second
data scan or cold process startup; use the underlying receipts' stage timings.

Full generated native integration is also opt-in. Supply
`NOVA_TEST_RESOLVER_ROOT`, `NOVA_TEST_EXPORT_PYTHON` and
`NOVA_TEST_ARTIFACT_ROOT` alongside the gateway root. The artifact root must be
new; the test preserves its generated minute partition, PNGs and receipts for
visual inspection. No historical market partition is used. This path has passed
with the real SDK, resolver, native renderer and verified zero active owned
processes. The integration test decodes the actual SDK image content and compares
its SHA256 to the verified detail manifest, preserving that exact PNG for visual
review. Refer to the PR verification record for test totals, observed cold-stage
timings and the Windows Store executable-alias fix.
