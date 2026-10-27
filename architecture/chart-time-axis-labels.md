# Chart time-axis labels: whole or not drawn (#459)

Owner: `frontend/src/chart/timeAxisEdgeLabels.ts`, installed by
`frontend/src/chart/useChartInstance.ts` on every chart it builds (10-second,
1-minute, 5-minute and daily panes). The indicator panes hide their time axis
and are not covered.

## The rule

A time-axis label is drawn whole, centred on its own tick, or it is not drawn.
A label that would cross either edge of the axis is left out; its tick and grid
line stay, and the next label along shows in full. Labels are never shifted off
their tick to fit, because a shifted label names a time its tick is not at and
can overlap its neighbour. The crosshair's time label is on its own canvas and
is not affected.

## Why Nova does this, not the library

lightweight-charts (5.1.0) centres each tick label on its tick. It pulls an edge
label inward only while scrolling is locked (`fixLeftEdge` / `fixRightEdge`, or
all scale and scroll handling off). Nova's charts scroll freely, so a tick near
either edge drew past the axis canvas and was cut: `2026` read `026`,
`10:00 AM` read `10:00 A`. Every pane and width did this, not one viewport.

Two cheaper-looking fixes do not hold:

- **Blanking the label from `tickMarkFormatter`.** The library caches formatted
  labels by time, so a label blanked at the edge stays blank after scrolling
  inward.
- **`fixLeftEdge` / `fixRightEdge`.** This changes scrolling, and it still only
  aligns the first and last labels of the data.

## What the guard depends on

The guard wraps `fillText` on the time axis's label canvas (an own property on
that one context, removed when the chart is disposed). It acts only on
centre-aligned text, which on that canvas is the tick labels. It finds the
canvas from the public `chart.chartElement()` and the library's axis layout: the
chart table's last row is the time axis (left stub, axis cell, right stub), and
the axis cell's first canvas holds the tick labels.

If a lightweight-charts upgrade changes that layout or how it draws tick labels,
the guard stops working and does nothing else. `frontend/e2e/chart-time-axis-labels.spec.ts`
is the check: it sweeps Nova's own chart across scroll positions at 320 / 480 /
800 px and DPR 1 / 1.5, and fails if any drawn label crosses the axis edge or if
year, day and clock labels stop appearing. Run it after any lightweight-charts
upgrade or any change to the chart's time-scale options.
