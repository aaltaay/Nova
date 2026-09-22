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
  type DrawingOptions,
  type IDrawing,
} from 'lightweight-charts-drawing';

// Style matches the chart's own crosshair color.
export const CHART_DRAWING_STYLE = { lineColor: '#3b82f6', lineWidth: 1 };

/**
 * Options every Nova drawing is created with.
 *
 * `showPrice: false` suppresses the library's in-plot price label, which it
 * paints left-aligned at `plotWidth - 10` and therefore clips to a couple of
 * characters. The price is published on the price axis instead --
 * `chartDrawingAxisLabel.ts`.
 *
 * `showPrice` lives on the price-level tools' own option types, not on the base
 * `DrawingOptions`; the tools without it ignore the key, which keeps one
 * creation path instead of a per-tool branch at every construction site.
 */
export type ChartDrawingOptions = Partial<DrawingOptions> & { showPrice?: boolean };
export const CHART_DRAWING_OPTIONS: ChartDrawingOptions = { showPrice: false };

/** Text colour of the axis chip Nova draws in its place. */
export const CHART_DRAWING_AXIS_LABEL_TEXT_COLOR = '#ffffff';

/** Library `type` strings whose first anchor is a price level worth an axis chip. */
export const CHART_PRICE_LEVEL_DRAWING_TYPES: ReadonlySet<string> = new Set([
  'horizontal-line',
  'cross-line',
]);

/** Preset palette for the selection color picker (compact: 8 swatches). */
export const CHART_DRAWING_COLORS: readonly string[] = [
  '#3b82f6', // blue (default)
  '#ef4444', // red
  '#22c55e', // green
  '#f59e0b', // amber
  '#a855f7', // purple
  '#06b6d4', // cyan
  '#f97316', // orange
  '#ffffff', // white
];

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
  options?: ChartDrawingOptions,
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
