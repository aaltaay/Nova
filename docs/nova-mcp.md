# Nova MCP: data and desk charts

One server answers the research data tools and the desk chart tools.

```text
py -3 tools/nova_mcp.py
```

On Linux, `python3 tools/nova_mcp.py` is the same command. `py -3 tools/nova_data_mcp.py` starts this same server, so an existing data config keeps working. `tools/nova_chart_mcp.py` is still the older candle-and-volume exporter.

The process speaks MCP on stdin/stdout. It does not open a port or a browser until a chart tool runs. The first chart call starts one shared review listener (default `http://127.0.0.1:18765/api/review`). Later clients on this machine reuse that listener. Pass `--review-http` or set `NOVA_REVIEW_HTTP=1` to start it before any chart call. `--no-review-http` never listens. Chromium starts on the first `png` or `both` call, not at process start.

Port 8765 is the research downloads page. The review listener does not use it. If 18765 is already taken by something else, the listener binds a free port and prints that URL. Chart links then carry `api=` so the page fetches that origin. `NOVA_REVIEW_PORT` changes the preferred port.

Open the desk (a second terminal):

```text
cd frontend
npm run dev
```

Vite proxies `/api/review` to `NOVA_REVIEW_API` (default `http://127.0.0.1:18765`). Then open a chart:

```text
http://127.0.0.1:5173/review?symbol=IMCC&date=2026-09-18&tf=1m,5m,1d
```

A gallery is the same page with `symbols=A,B,C` instead of `symbol`. The grid draws one timeframe (5-minute when that was requested) and the header says which one. Each cell still links to the full page. Add `&fixture=1` to draw a labelled sample session when the Massive files are not on this machine.

`NOVA_REVIEW_BASE` (default `http://127.0.0.1:5173`, flag `--review-base`) is the origin written into chart URLs. `--output-root` is where `output_name` tables and review PNGs are written. Old PNGs are deleted once the folder passes 24 files or 8 MB.

## Data tools

The 22 data tools keep their names, arguments, units and as-of rules. Start with `data_catalog`. A long read such as `data_status` takes only its own lock, so `movers_search` is not stuck behind it. Heavy disk reads still share the PC-wide slots.

## Chart tools

`nova_historical_chart`, `nova_historical_chart_gallery` and `nova_trade_charts` take `output`:

| output | What you get |
|---|---|
| `interactive` (default) | `/review` URLs only. One URL per symbol, plus one gallery URL. No bars are loaded. A batch of 9 symbols returns in one fast call. Each page loads its own data when you open it. |
| `png` | A screenshot of that same `/review` page, returned as an MCP image block and written under the output root. One symbol does not also shoot the gallery page. The browser starts on this call and stays for the life of the server. |
| `both` | The URLs and the screenshots. This waits on the pictures. |

`tf` is `1m`, `5m`, `10s`, `1d`. The default view is the 1-minute, 5-minute and daily panes. `as_of` is `HH:MM` Eastern (default `16:00`). Bars that have not closed by then are left out. VWAP starts at 04:00. The session day's daily candle is built from those minutes, not from the official daily row, which can include later prints.

There is no order button and no live quote subscription on `/review`. The trading desk is a different page.

Screenshots need Node, Playwright and Chromium (`cd frontend && npx playwright install chromium`). If those are missing, a PNG call returns `REVIEW_SHOT_UNAVAILABLE` and the interactive links still work.
