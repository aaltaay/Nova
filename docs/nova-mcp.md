# Nova MCP: data and desk charts

One server answers the research data tools and the desk chart tools.

```text
py -3 tools/nova_mcp.py
```

On Linux, `python3 tools/nova_mcp.py` is the same command. `py -3 tools/nova_data_mcp.py` starts this same server, so an existing data config keeps working. `tools/nova_chart_mcp.py` is still the older candle-and-volume exporter.

The process speaks MCP on stdin/stdout. It does not open a port or a browser until `nova_chart` runs. That call starts one review engine for the whole PC (`tools/nova_review_engine.py`, default `http://127.0.0.1:18765`). Later MCP processes attach to it. The engine outlives the client that started it, serves the built review page from `frontend/dist`, and exits after 30 minutes with no requests. Pass `--review-http` or set `NOVA_REVIEW_HTTP=1` to start it before any chart call. `--no-review-http` never listens. `--no-warm-shots` still returns links, with `Preview images unavailable: REVIEW_SHOT_UNAVAILABLE`.

Port 8765 is the research downloads page. The review engine does not use it. If 18765 is already taken by something else, the engine binds a free port and the chart link carries `api=`. `NOVA_REVIEW_PORT` changes the preferred port.

Open the desk (a second terminal), or skip this when `frontend/dist` is already built. The engine serves that build itself.

```text
cd frontend
npm run dev
```

Vite proxies `/api/review` to `NOVA_REVIEW_API` (default `http://127.0.0.1:18765`). Then open a chart:

```text
http://127.0.0.1:5173/review?symbol=IMCC&date=2026-09-18&tf=10s,1m,5m,1d
```

A gallery is the same page with `symbols=A,B,C` instead of `symbol`. Tabs are `10s`, `1m`, `5m`, `1d` (`gtf` in the URL, default `5m`). Each cell is the desk chart for that timeframe and links to the four-pane page. Add `&fixture=1` to draw a labelled sample session when the Massive files are not on this machine.

`NOVA_REVIEW_BASE` (flag `--review-base`) is the origin written into chart URLs when you set it. When you leave it unset, the link uses the review engine's own origin, the process that serves `/review`. `--output-root` is where `output_name` tables and the copies of review PNGs are written. The engine keeps its own PNGs in a temp review-shots folder and deletes old ones, under a lock, once that folder passes 24 files or 8 MB. A PNG is written only after its real path stays inside that folder, and rotation only deletes files when the folder is under the system temp directory.

## Data tools

The 25 data tools keep their names, arguments, units and as-of rules (the three relative-volume tools, `rvol_scan`, `rvol_triggers` and `rvol_outcomes`, read the table `research/rvol/build_rvol.py` builds; `docs/market-data.md`, "Relative volume across every stock"). Start with `data_catalog`. A long read such as `data_status` takes only its own lock, so `movers_search` is not stuck behind it. Heavy disk reads still share the PC-wide slots.

## Chart tool

One tool: `nova_chart`.

| Argument | Required | Meaning |
|---|---|---|
| `symbols` | yes | 1 to 9 tickers |
| `date` | yes | `YYYY-MM-DD` |
| `as_of` | no | `HH:MM` Eastern, default `16:00` |

Any other argument (`tf`, `output`, `symbol`, `trades`, and the rest) is rejected. The error text starts with `UNKNOWN_ARGUMENT`. Timeframes are always `10s`, `1m`, `5m`, `1d`, for the full session from 04:00 to 16:00 ET. The page uses the desk chart with the desk's usual overlays.

The tool result is, in order:

1. A text block. Post it as-is. It is `chat_message`:
   `Nova charts for {date}, as of {as_of} ET (10s, 1m, 5m, 1d, full session):`
   then `- {SYMBOL}: {url}` for each symbol, then `Gallery: {url}` when there is more than one symbol, then `Preview images unavailable: {code}` only when a PNG failed.
2. PNG image blocks. One per symbol (that symbol's four-pane page). When there is more than one symbol, one more image of the gallery's 5-minute tab.
3. JSON: `ok`, `chat_message`, `date`, `as_of`, `timeframes`, `links`, `gallery_url`, `images` (`symbol`, `sha256`, `bytes`). On failure `ok` is false and `error` is `{code, detail}`. The text still lists the links. `REVIEW_DESK_UNREACHABLE` means the review page could not be opened for the screenshot. A clock that is not `HH:MM` (a full-width colon counts) is `BAD_REQUEST`.

Building the links does not load bars. `nova_historical_chart`, `nova_historical_chart_gallery` and `nova_trade_charts` are not on this server.

There is no order button and no live quote subscription on `/review`. The trading desk is a different page. The review bundle does not load the bots page or the bot allowlist, and it loads the sample fixture only when the URL says `fixture=1`.

The screenshot route is not a public browser form. The engine writes a random token into its lease file. Only a local MCP process reads that file and sends it as `X-Nova-Review-Token`. The request must be JSON, must not carry an `Origin` header, and must not name a URL or a file path. The engine builds the page address and the PNG path itself. Files under `/assets/` stay inside `frontend/dist`.

Screenshots need Node, Playwright and Chromium (`cd frontend && npx playwright install chromium`). If those are missing, the text says `Preview images unavailable: REVIEW_SHOT_UNAVAILABLE` and the links are still there.
