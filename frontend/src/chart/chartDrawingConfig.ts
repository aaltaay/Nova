/** ADR 005 — drawing tool registry for lightweight-charts-drawing. */

import {
  HorizontalLine,
  VerticalLine,
  CrossLine,
  type Anchor,
  type IDrawing,
} from 'lightweight-charts-drawing';

// Style matches the chart's own crosshair color.
export const CHART_DRAWING_STYLE = { lineColor: '#3b82f6', lineWidth: 1 };

/** Single-click drawing tools (1 anchor each). TrendLine needs 2 anchors separately. */
export const CHART_SINGLE_ANCHOR_TOOLS: Record<
  string,
  new (id: string, anchors: Anchor[], style: typeof CHART_DRAWING_STYLE) => IDrawing
> = {
  HorizontalLine,
  VerticalLine,
  CrossLine,
};
