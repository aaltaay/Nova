/**
 * Time-axis labels are drawn whole or not at all (#459).
 *
 * lightweight-charts centres each tick label on its tick and pulls the edge
 * labels inward only while scrolling is locked (`fixLeftEdge` /
 * `fixRightEdge`). Nova's charts scroll freely, so a tick near either edge of
 * the pane drew a cut label: `2026` read `026`, `10:00 AM` read `10:00 A`.
 * A label that would cross the axis edge is left out instead; its tick and
 * grid line stay, and the crosshair label (its own canvas) is untouched.
 *
 * Contract and its dependency on the library's canvas layout:
 * `architecture/chart-time-axis-labels.md`.
 */

import type { IChartApi } from 'lightweight-charts';

/** Sub-pixel slack so a label that exactly fills the edge still draws. */
const EDGE_SLACK_PX = 0.5;

/**
 * The time axis's label canvas: the chart table's last row is the time axis
 * (left stub, axis cell, right stub); the axis cell's first canvas holds the
 * tick labels, the second the crosshair.
 */
function timeAxisLabelCanvas(chart: IChartApi): HTMLCanvasElement | null {
  const table = chart.chartElement().querySelector('table');
  const axisRow = table?.rows[table.rows.length - 1];
  return axisRow?.cells[1]?.querySelector('canvas') ?? null;
}

/** True when a centred label at `x` fits inside an axis `axisWidth` wide. */
export function timeAxisLabelFits(x: number, labelWidth: number, axisWidth: number): boolean {
  const half = labelWidth / 2;
  return x - half >= -EDGE_SLACK_PX && x + half <= axisWidth + EDGE_SLACK_PX;
}

/** Leave out tick labels that would draw past the time axis's edges. Returns the undo. */
export function keepTimeAxisLabelsWhole(chart: IChartApi): () => void {
  const canvas = timeAxisLabelCanvas(chart);
  const ctx = canvas?.getContext('2d');
  if (!canvas || !ctx) return () => {};
  const drawText = ctx.fillText;
  ctx.fillText = (text: string, x: number, y: number, maxWidth?: number) => {
    // Tick labels are drawn centred in CSS pixels (the media transform scales x).
    if (ctx.textAlign === 'center') {
      const axisWidth = canvas.width / (ctx.getTransform().a || 1);
      if (!timeAxisLabelFits(x, ctx.measureText(text).width, axisWidth)) return;
    }
    if (maxWidth === undefined) drawText.call(ctx, text, x, y);
    else drawText.call(ctx, text, x, y, maxWidth);
  };
  return () => {
    delete (ctx as { fillText?: unknown }).fillText;
  };
}
