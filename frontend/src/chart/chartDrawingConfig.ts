/** ADR 005 — drawing tool registry for lightweight-charts-drawing. */

import {
  ExtendedLine,
  HorizontalLine,
  HorizontalRay,
  Ray,
  TrendLine,
  VerticalLine,
  CrossLine,
  type Anchor,
  type IDrawing,
} from 'lightweight-charts-drawing';

// Style matches the chart's own crosshair color.
export const CHART_DRAWING_STYLE = { lineColor: '#3b82f6', lineWidth: 1 };

export interface ChartLineToolDefinition {
  id: string;
  label: string;
  hotkey: string;
  key: string;
}

export const CHART_LINE_TOOLS: readonly ChartLineToolDefinition[] = [
  { id: 'TrendLine', label: 'Trendline', hotkey: 'Alt+T', key: 't' },
  { id: 'HorizontalLine', label: 'Horizontal Line', hotkey: 'Alt+H', key: 'h' },
  { id: 'VerticalLine', label: 'Vertical Line', hotkey: 'Alt+V', key: 'v' },
  { id: 'ExtendedLine', label: 'Extended', hotkey: 'Alt+E', key: 'e' },
  { id: 'Ray', label: 'Ray', hotkey: 'Alt+J', key: 'j' },
  { id: 'HorizontalRay', label: 'Horizontal Ray', hotkey: 'Alt+R', key: 'r' },
];

type DrawingConstructor = new (
  id: string,
  anchors: Anchor[],
  style: typeof CHART_DRAWING_STYLE,
) => IDrawing;

/** Drawing tools completed by one chart click. */
export const CHART_SINGLE_ANCHOR_TOOLS: Record<
  string,
  DrawingConstructor
> = {
  HorizontalLine,
  HorizontalRay,
  VerticalLine,
  CrossLine,
};

/** Drawing tools completed by two chart clicks. */
export const CHART_TWO_ANCHOR_TOOLS: Record<string, DrawingConstructor> = {
  TrendLine,
  ExtendedLine,
  Ray,
};
