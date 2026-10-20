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

`NOVA_REVIEW_BASE` (default `http://127.0.0.1:5173`, flag `--review-base`) is the origin written into chart URLs. `--output-root` is where `output_name` tables and review PNGs are written. Old PNGs are deleted once the folder passes 24 files or 8 MB.

## Data tools

The 22 data tools keep their names, arguments, units and as-of rules. Start with `data_catalog`. A long read such as `data_status` takes only its own lock, so `movers_search` is not stuck behind it. Heavy disk reads still share the PC-wide slots.

## Chart tool

Chart tool: `nova_chart`. Open tool: `open_in_nova` (below).

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
3. JSON: `ok`, `chat_message`, `date`, `as_of`, `timeframes`, `links`, `gallery_url`, `images` (`symbol`, `sha256`, `bytes`). On failure `ok` is false and `error` is `{code, detail}`. The text still lists the links. `REVIEW_DESK_UNREACHABLE` means the page at `NOVA_REVIEW_BASE` could not be opened for the screenshot.

Building the links does not load bars. `nova_historical_chart`, `nova_historical_chart_gallery` and `nova_trade_charts` are not on this server.

There is no order button and no live quote subscription on `/review`. The symbol name is a button that opens that day in Nova. The trading desk is a different page.

## Open tool

One more tool: `open_in_nova`.

| Argument | Required | Meaning |
|---|---|---|
| `symbol` | yes | one ticker |
| `date` | yes | `YYYY-MM-DD` |
| `as_of` | no | `HH:MM` or `HH:MM:SS` Eastern |

Any other argument is rejected. The error text starts with `UNKNOWN_ARGUMENT`. The tool calls the desk's existing show command, which opens the running Nova desk in the Sim, paused, on that symbol and day. Post `chat_message` as-is. It is one of:

- `Opened {SYMBOL} in Nova Sim on {date} at {HH:MM:SS} ET, paused.`
- `Opened {SYMBOL} in a separate Sim window on {date} at {HH:MM:SS} ET, paused. The live desk stayed on its own view.`

During regular hours (09:30 to 16:00 ET on a trading day, 16:00 not included) Nova opens a separate window and leaves the live desk where it is. Outside those hours the main view switches to Sim. The tool does not place, change, or cancel an order. If the desk is closed the text is `Nova's desk is not running. Start it with scripts/windows/Run Nova Desktop.bat, then ask again.` Start the desktop app, then ask again. Nova does not launch it for you.

Screenshots need Node, Playwright and Chromium (`cd frontend && npx playwright install chromium`). If those are missing, the text says `Preview images unavailable: REVIEW_SHOT_UNAVAILABLE` and the links are still there.
