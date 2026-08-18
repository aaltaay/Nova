# 2026-08-18 -- Chart viewport after store-first

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed
- **Related:** `CHANGELOG.md` §2026-08-18 -- Chart panes paint history instead of the live tip · `PROBLEM_LOG.md` §2026-08-18 -- Chart history arrived but panes stayed on the live tip · ADR 012

## Task

Soak Trader charts after ADR 012. The user still saw long loads and empty/gapped panes (CDTG 5Min/10Sec/Full Day).

## Goal

History that is already in the IBKR store must be visible in all four Trader panes within a couple of seconds, without the old timeout overlay.

## Why it mattered

The architecture change removed the red timeout but the desk still looked broken. The problem had shifted from "no request" to "request landed, viewport hid it."

## What we changed

- Do not invent the first candle from a live tick.
- After every full `setData`, apply a session-sized window (5Min last 96 bars; 1Min/10Sec `fitContent`).
- MACD/RSI follow the price chart only; they do not push last-N back up.
- Shared `ensureBars` HTTP is not aborted by one pane's cleanup.
- `bars_store.read` no longer uses tape `bars_1m` / `bars_1d`.
- Stub intraday series are not treated as a finished fill.
- Daily bars survive `rawBarsToIndicatorBars`.
- Coverage clock is ET, not a UTC slice labeled ET.
- Restarted the local API so the ADR 012 worker was actually serving.

## How it works now

Click / Trader open is still a local store read. Fills still arrive as `bars_patch`. Painting a full series always sets the visible logical range (or fits when the series is already session-sized). One pane aborting does not cancel the other panes' HTTP. Tape archive is not a chart hit.

## Why this approach

Fitting every `setData` and ignoring MACD's default last-N range is less "clever" than trying to preserve user zoom across background rewrites. The rewrite is what made the panes look empty. Rejected: another timeout/retry on `/bars` (the store already had the data). Rejected: keeping tape `bars_1m` as a fallback (ADR 012 already called that out; CDTG had one tape row and that blocked the real 1Min fill).

## Verification

- `npx vitest run src/tickerChartData.test.ts src/chart/liveTradeApply.test.ts src/chart/barsStore.test.ts src/chartIndicators.test.ts` -- 32 passed
- `py -3 -m pytest backend/tests/test_bars_store.py backend/tests/test_historical_service.py -q` -- 7 passed
- Live `/api/ticker/CDTG/bars` after API restart: 1Min 492, 5Min 500, 10Sec 1464, 1Day 500, all with `coverage`
- Playwright soak `/?view=stock&symbol=CDTG` (2s / 10s / 25s), AAPL, CDTG return: all four panes populated; no page errors

## Follow-ups

- Reload backend whenever `/bars` lacks `coverage` (old sidecar).
- 10Sec can still show an empty pre-session block on LWC's time axis; that is calendar empty, not a missed fetch.

## Keywords

chart, viewport, fitContent, CDTG, bars_patch, MACD, bars_1m, 1Day, soak, ADR 012
