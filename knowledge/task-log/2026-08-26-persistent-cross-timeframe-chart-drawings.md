# 2026-08-26 — Persistent cross-timeframe chart drawings (ADR 015)

- **Status:** completed
- **Agents:** parent
- **Domain:** charts / market-feed-adjacent (operator annotations, not market data)
- **Related:** `CHANGELOG.md` 2026-08-26 — Chart drawings are shared across timeframes and survive restart · `PROBLEM_LOG.md` 2026-08-26 (two entries) · `architecture/decisions/015-persistent-chart-drawings.md`

## Task

"When I draw a horizontal line in any chart, I want it to show in all timelines. And I want that line/drawing to be kept and survive shutdown/reboot."

## Goal

A drawing placed on one pane appears on every timeframe pane for that symbol, and the whole set survives page reload, API restart, and machine reboot. The operator chose backend storage (over localStorage) and asked for all four tools to be shared, not just horizontal lines.

## Why it mattered

Marked levels are working memory. Before this, one symbol had up to five disconnected drawing sets (the Trader 2x2 grid's four panes plus the Quote Panel chart), so a support level marked on the 1Min pane was invisible on the 1D pane — the operator had to redraw the same level per pane and lost all of it on every reload. Two related defects rode along: drawings were never cleared on symbol change, so AAPL levels stayed painted over TSLA, and nothing was persisted anywhere at all.

## What we changed

- **Backend store:** `backend/chart_drawings.py` — sole owner of `backend/.cache/chart-drawings.json`, `schema_version` 1, refuse-loud on unknown version, sanitizes to the five `SerializedDrawing` fields, per-symbol and per-anchor caps. One bad row on load is dropped with a warning instead of costing the operator every other level.
- **REST:** `backend/routes/chart_drawings.py` — `GET`/`PUT`/`DELETE /api/chart-drawings/{symbol}`, registered in `app_routers.py`. `PUT` replaces the symbol's whole list.
- **Cache I/O + constants:** `cache.py` `save_/load_chart_drawings`, `constants_scanner.py` `CHART_DRAWINGS_*`, frontend `market_ui.ts` `CHART_DRAWINGS_*`.
- **Shared frontend store:** `chartDrawingsStore.ts` — per-symbol map, synchronous listener fan-out, deduped `GET`, debounced `PUT`, `BroadcastChannel` + focus refetch for detached windows, monotonic revision counter.
- **Cross-timeframe time mapping:** `chartDrawingTime.ts` — canonical epoch conversion and snap-to-nearest-bar with edge clamping.
- **Hydrate policy:** `chartDrawingHydrate.ts` — the `shouldHydrateDrawings` rule plus the `ToolRegistry` rebuild factory.
- **Hook rewrite:** `useChartDrawingManager.ts` hydrates from the store, writes back per changed drawing, and clears on symbol change. `TickerChart.tsx` moved the hook below `useChartBars` so the painted series exists when hydrating.
- **Test isolation:** `backend/tests/conftest.py` pins `CHART_DRAWINGS_FILE` to the temp cache so pytest never writes the operator's drawings.

## How it works now

Invariants a cold agent should hold:

1. **The store is the truth; the manager is a view.** `DrawingManager` stays per-pane because it owns hit testing against one canvas. Only its contents come from `chartDrawingsStore`, keyed by symbol. Sharing happens because a store mutation notifies every subscribed pane synchronously.
2. **One canonical anchor time, snapped per pane.** Storage is always ET-shifted epoch seconds. On hydrate, each pane maps that epoch to its own nearest painted bar time. This is mandatory, not cosmetic: intraday series carry epoch numbers, 1Day+ series carry `'YYYY-MM-DD'` strings, and `timeScale.timeToCoordinate` returns `null` for an off-scale time — every tool except `HorizontalLine` refuses to paint on that `null`.
3. **Out-of-window anchors clamp to the edge bar, never drop.** A level pinned at the chart edge is honest; a level that vanished is the bug being fixed.
4. **Only the pane that caused a change writes it.** Each pane records the store revision it produced. A revision it did not produce means a sibling edited, so rebuild. This is what stops a 1Day pane from flattening every 1Min-precision anchor, and stops the drawing pane from wiping the line it just placed.
5. **A local edit beats an in-flight `GET`.** `fetchDrawings` discards a server payload whose revision moved while the request was pending.
6. **Nothing stales drawings except an explicit `PUT`/`DELETE`.** Deliberately unlike every other Nova cache — no session rollover, reconnect generation, or scanner freeze touches them.

## Why this approach

**Backend JSON over localStorage.** localStorage does survive a reboot, so it met the literal ask and was far less work. Rejected because it is per-browser-profile, is lost with browser data, and gives detached Trader windows (separate renderer processes) no server-side truth to reconcile against. The operator explicitly chose the backend when asked. It also satisfies `persisted-state.mdc` (owner + invalidation trigger + `schema_version`), which localStorage would not.

**One canonical time + snap-on-load, over storing a copy per timeframe.** Per-timeframe copies are the current broken model with persistence bolted on: the same level multiplied five ways, with no way to express "this is *the* level." The snap approach keeps a single identity per level. The cost is real and accepted: dragging a *time-anchored* drawing on a coarse pane saves that pane's resolution. Horizontal lines — the common case and the actual ask — carry no loss because only price matters.

**Snapping at all, rather than storing the raw `Time` the pane produced.** Verified in the library source before writing code: `Drawing.anchorToPixel` returns `null` if either coordinate is `null`, and the `VerticalLine`/`TrendLine`/`CrossLine` pane views bail on it. `HorizontalLine`'s renderer is the one exception (price only). Without snapping, three of the four tools would silently paint nothing on any pane other than the one that drew them — the exact invisible failure this job exists to remove.

**Per-drawing write-back over whole-list write-back from the client.** Whole-list would be simpler and always self-consistent, but a daily pane's export canonicalizes every anchor to midnight, so a single edit there would flatten the time precision of every other drawing on that symbol. Hence the revision-claim mechanism.

**Whole-list replace on the `PUT` (server side), though.** The client's source of truth is `exportDrawings()` — a full snapshot. Per-drawing REST CRUD would add a reconciliation problem with no caller that needs it.

**`series.createPriceLine()` rejected for horizontal levels.** Not draggable, not selectable, and it would need a persistence path separate from the other three tools. It stays reserved for the fixed RSI reference levels in `TickerChartOscillatorPanes.tsx`.

## Verification

- `py -3 -m pytest -q` → **1384 passed** (24 new). Confirmed the 24 are mine by re-running with both new files ignored → 1360 passed. The background-thread `faulthandler` dump in the output is pre-existing (it appears with my files excluded too), not something this change introduced.
- `npx vitest run` → **816 passed**, plus 33 new chart-drawing tests (`chartDrawingTime` 18, `chartDrawingsStore` 15, `chartDrawingHydrate` 10 — 112 total in `src/chart/`).
- `npx tsc --noEmit -p tsconfig.app.json` → exit 0. `npm run build` → exit 0.
- Live HTTP round-trip against the local API: `PUT` then `GET` returned the stored line; a second symbol returned `[]`; `DELETE` emptied it; `chart-drawings.json` on disk carried `schema_version: 1`.
- **Operator confirmation in-app** (the decisive evidence): a horizontal line *and* a trend line drawn on CRE persisted with canonical anchors — `horizontal-line` @ 7.1198, `trend-line` 8.2207 → 5.6887.
- A `browser-use` subagent reported the feature non-functional. That report was wrong: its synthetic canvas click never reached lightweight-charts' `subscribeClick`, and its root-cause claim ("backend communication failure") contradicted its own evidence that `/api/chart-drawings/SPY` answered `200`; it had also probed `/health` instead of `/api/health`. The operator's manual test superseded it. The investigation was still worth it — it surfaced the in-flight-`GET` race, a genuine defect in my own code, which is now fixed and regression-tested.

## Follow-ups

- Ops note, not caused by this change: a `run_api.py` process (pid 48124) was found holding the instance lock with 293 sockets and **no listener** while `:8000` actively refused connections. Stopped deliberately after confirming it was not serving — this is not the "loop starve" case the IBKR rule protects, since there was no listener at all.
- Deferred: a drawing style/color picker, and including drawings in the prefs export bundle. Neither was asked for.
- Do not reopen the per-timeframe-copies design without re-reading ADR 015's rejected alternatives.

## Keywords

chart drawings, horizontal line, trend line, DrawingManager, lightweight-charts-drawing, timeToCoordinate, snap to bar, canonical epoch, ET-shifted, cross-timeframe, persistence, schema_version, chart-drawings.json, symbol bleed, revision, ADR 015
