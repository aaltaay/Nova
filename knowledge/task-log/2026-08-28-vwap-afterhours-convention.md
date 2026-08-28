# 2026-08-28 -- Park after-hours VWAP convention (D-007)

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed / chart UI (continuity-only; no specialist hop)
- **Related:** `DEFERRED_LOG.md` D-007; `CHANGELOG.md` 2026-08-28 -- Chart VWAP starts at 04:00 ET premarket

## Task

Decide whether after-hours (16:00-20:00) should keep adding to the 04:00 VWAP or stay frozen at the cash close. Operator said do not invent -- match other charts.

## Goal

Record what Webull / Robinhood / TradingView / DAS actually do, park a change, make no paint edits.

## Why it mattered

A silent flip of `CHART_VWAP_SESSION_END_SEC` (or a second series) would change the orange line every after-hours session. Operator did not want that until the consequences are clear.

## What we changed

- Parked `D-007` in `DEFERRED_LOG.md` (Status: parked, Kind: decision)
- Cross-linked from the 04:00 CHANGELOG entry and the premarket task-log
- No `vwapSession.ts` / constant edits

## How it works now

Nova still accumulates 04:00-16:00 ET and carries the 16:00 value after the close. That is one valid industry pattern (TradingView with extended hours off; institutional cash VWAP is done at 16:00). Webull and DAS reset and draw a separate after-hours VWAP. TradingView with Extended Hours on keeps adding. Robinhood docs never state session bounds. There is no single universal rule.

## Why this approach

Writing D-007 instead of picking a side. "Keep adding" would mix thin after-hours prints into the daytime number -- Webull and DAS specifically avoid that. A second AH line is a real product change (extra series, overnight gap rules). Freeze is already shipped and matches "session VWAP ends at the cash close."

## Verification

Research only -- TradingView VWAP help, DAS VWAP docs (pre/post checkbox = extra line), community Webull-style segmented VWAP, Robinhood indicator list, r/Daytrading platform spread. No new tests; no browser paint change.

## Follow-ups

After the cash close, screenshot Nova vs Webull on the same 1Min. Then pick freeze / second AH line / keep adding. Do not start from `CHART_VWAP_SESSION_END_SEC` without that look.

## Keywords

vwap, after-hours, 16:00, Webull, DAS, TradingView, D-007, session convention
