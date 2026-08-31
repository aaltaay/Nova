# ADR 015 — Persistent, cross-timeframe chart drawings

**Status:** Accepted · **Date:** 2026-08-26

## Context

Nova's chart drawing tools (Trendline, Horizontal Line, Vertical Line, Extended Line,
Ray, Horizontal Ray, and Crosshair) are provided by `lightweight-charts-drawing`,
driven by `frontend/src/chart/useChartDrawingManager.ts`.
Each `TickerChart` instance constructed its own `DrawingManager`. Because the Trader desk
renders a 2x2 multi-timeframe grid (`ChartGrid.tsx`) and the scanner Quote Panel renders a
fifth chart, one symbol had up to five independent, disconnected drawing sets. A support
level marked on the 1Min pane was invisible on the 5m, 1D, and 10Sec panes.

Nothing was persisted. The manager lived in a `useEffect` and was destroyed on unmount, so
every drawing died on reload, on a Desktop restart, and on a reboot. Two related defects
followed from the same gap:

1. **Symbol bleed.** The manager was never cleared on symbol change, so a level drawn on
   AAPL stayed painted over TSLA (see `PROBLEM_LOG.md` 2026-08-26).
2. **No shared identity.** With no store, there was no way to express "this level belongs
   to this symbol" independent of which pane happened to draw it.

The hard technical constraint is that panes do not agree on what a `Time` is.
`tickerChartData.isoToEtTime` returns ET-shifted epoch **numbers** for intraday timeframes
and `'YYYY-MM-DD'` business-day **strings** for 1Day/1Week/1Month. Every drawing except the
horizontal line resolves its anchor through `timeScale.timeToCoordinate`, which returns
`null` for a time absent from that pane's scale — so a 1Min anchor of `1756…` renders
nothing at all on a 1Day chart. Verified in the library source: `Drawing.anchorToPixel`
returns `null` when either coordinate is `null`, and `VerticalLine` / `TrendLine` / `CrossLine`
pane views bail on that `null`. `HorizontalLine`'s renderer is the sole exception — it reads
only `priceScale.priceToCoordinate`.

## Decision

1. **Drawings are stored per symbol on the backend**, in `backend/.cache/chart-drawings.json`
   owned solely by `backend/chart_drawings.py`, with `schema_version` and refuse-loud on an
   unknown version (`.cursor/rules/persisted-state.mdc`). REST surface is
   `GET`/`PUT`/`DELETE /api/chart-drawings/{symbol}`.

2. **Invalidation trigger is an explicit `PUT`/`DELETE` only.** Drawings are deliberately
   session-independent: a level marked on Friday is still that level on Monday, so no
   session rollover, reconnect generation, or scanner freeze stales them. This is a
   departure from every other Nova cache and is intentional.

3. **`PUT` replaces a symbol's whole list**, because the client's source of truth is
   `DrawingManager.exportDrawings()` — a full snapshot. Per-drawing CRUD would add a
   reconciliation problem with no caller that needs it.

4. **One canonical anchor time (ET-shifted epoch seconds), snapped per pane on load.**
   `frontend/src/chart/chartDrawingTime.ts` converts any series `Time` to a canonical epoch
   for storage, and maps a stored epoch to the target pane's nearest real bar time on
   hydrate. An anchor outside a pane's window clamps to the first/last bar: a level pinned
   at the chart edge is honest, a level that silently vanished is not.

5. **Only the pane that produced a change writes it.** `chartDrawingsStore` keeps a
   per-symbol revision counter; a pane records the revision it caused so it can distinguish
   its own echo from a sibling's edit. Without this, a coarse 1Day pane would rewrite every
   1Min-precision anchor on every hydrate, and the pane that just placed a line would
   immediately wipe and re-import it, dropping the operator's selection.

6. **A local edit beats an in-flight `GET`.** `fetchDrawings` captures the revision at
   request start and discards the server payload if the revision moved while the request was
   pending. A slow API must never erase a line already on screen.

7. **The `DrawingManager` stays per-pane.** It owns hit testing against one canvas; only its
   *contents* are shared. Nothing about drawing interaction moves to a global.

8. **Symbol change clears and rehydrates**, closing the AAPL-over-TSLA bleed as a direct
   consequence of the store being symbol-keyed.

## Consequences

- A drawing placed on any pane appears on all of them for that symbol, and survives reload,
  API restart, and reboot.
- Editing a time-anchored drawing (trend/vertical/cross) *on a coarse pane* saves that
  pane's bar resolution — dragging a trend line on the 1D pane stores day-granularity
  anchors. Accepted: the operator is working at the resolution they can see. Horizontal
  lines, which are the common case, carry no such loss because only price matters.
- Anchor drags fire `drawing:updated` per mousemove; the store debounces into one `PUT`
  (`CHART_DRAWINGS_SAVE_DEBOUNCE_MS`).
- `CHART_DRAWINGS_MAX_PER_SYMBOL = 200` caps the file so a runaway client loop cannot grow
  it without bound; the backend refuses over-cap payloads with HTTP 400.
- A detached Trader window is a separate renderer process, so cross-window sync uses a
  `BroadcastChannel` ping plus a refetch on window focus. The ping carries only the symbol —
  the receiving window refetches rather than trusting the message body.

## Rejected alternatives

- **localStorage only.** Rejected — it does survive a reboot, but it is per-browser-profile,
  is lost with browser data, and gives detached Trader windows no server-side truth to
  reconcile against. The backend store also lets a future export/import treat drawings like
  any other operator artifact.
- **Store one copy per timeframe.** Rejected — that is the current broken behavior with
  persistence bolted on. It multiplies the same level by five and gives the operator no way
  to express "this is the level," which is the actual thing being marked.
- **Snap nothing; store the raw `Time` the pane produced.** Rejected on library evidence —
  `timeToCoordinate` returns `null` for an off-scale time, so trend/vertical/cross lines
  would silently not paint on any pane other than the one that drew them. Silent invisibility
  is exactly the failure mode this ADR exists to remove.
- **Drop anchors that fall outside a pane's bar window.** Rejected — clamping to the edge bar
  keeps the level visible and scrollable-to; dropping reproduces "my line disappeared."
- **Full-list write-back from whichever pane emitted an event.** Rejected — a daily pane's
  export canonicalizes every anchor to midnight, so one edit there would flatten the time
  precision of every other drawing on the symbol. Hence decision 5.
- **`series.createPriceLine()` for horizontal levels.** Rejected — it is not draggable, not
  selectable, and would need a parallel persistence path separate from the other three
  tools. `createPriceLine` stays reserved for fixed RSI reference levels
  (`TickerChartOscillatorPanes.tsx`).

## Related

- `architecture/decisions/012-local-first-chart-bars.md` — the store-first bar pipeline whose
  painted series supplies the snap grid.
- `.cursor/rules/persisted-state.mdc` — owner + invalidation trigger + `schema_version`
  contract this store satisfies.
- `.cursor/rules/single-market-data-feed.mdc` — unaffected: drawings are operator annotations,
  not market data, and this ADR adds no price source.
- `PROBLEM_LOG.md` 2026-08-26 — chart drawings bled across symbols.
- `backend/chart_drawings.py`, `backend/routes/chart_drawings.py`
- `frontend/src/chart/chartDrawingTime.ts`, `chartDrawingsStore.ts`, `chartDrawingHydrate.ts`
