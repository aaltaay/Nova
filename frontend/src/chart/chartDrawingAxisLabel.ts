/**
 * Price-level drawings wear their price on the price axis, not inside the plot.
 *
 * `lightweight-charts-drawing` paints its own label at `x = plotWidth - 10` with
 * `textAlign: 'left'`, so the text runs straight off the right edge of the pane
 * and only the first character or two survives -- `8.` for `8.42`. Nova turns
 * that label off (`showPrice: false`, see `CHART_DRAWING_OPTIONS`) and publishes
 * the level as a real lightweight-charts price line instead: the chip lands on
 * the price scale, aligned with every other axis label, on a scale that already
 * reserves a fixed width (`chartPriceScale.ts`) so it cannot be clipped.
 *
 * `lineVisible: false` because the drawing still paints its own line -- this
 * price line exists only to carry the axis label.
 */
import { LineStyle, type CreatePriceLineOptions } from 'lightweight-charts';
import type { SerializedDrawing } from 'lightweight-charts-drawing';
import {
  CHART_DRAWING_AXIS_LABEL_TEXT_COLOR,
  CHART_DRAWING_STYLE,
  CHART_PRICE_LEVEL_DRAWING_TYPES,
} from './chartDrawingConfig';

export interface DrawingAxisLevel {
  price: number;
  color: string;
}

/** First anchor of every drawing whose anchor IS a price level, by drawing id. */
export function drawingAxisLevels(
  drawings: readonly SerializedDrawing[] | null | undefined,
): Map<string, DrawingAxisLevel> {
  const levels = new Map<string, DrawingAxisLevel>();
  for (const drawing of drawings ?? []) {
    if (!drawing?.id || !CHART_PRICE_LEVEL_DRAWING_TYPES.has(drawing.type)) continue;
    const price = drawing.anchors?.[0]?.price;
    if (typeof price !== 'number' || !Number.isFinite(price)) continue;
    const color = drawing.style?.lineColor;
    levels.set(drawing.id, {
      price,
      color: typeof color === 'string' && color ? color : CHART_DRAWING_STYLE.lineColor,
    });
  }
  return levels;
}

export function drawingAxisLineOptions(level: DrawingAxisLevel): CreatePriceLineOptions {
  return {
    price: level.price,
    color: level.color,
    lineWidth: 1,
    lineStyle: LineStyle.Solid,
    lineVisible: false,
    axisLabelVisible: true,
    axisLabelColor: level.color,
    axisLabelTextColor: CHART_DRAWING_AXIS_LABEL_TEXT_COLOR,
    title: '',
  };
}

export interface AxisLevelDiff {
  added: string[];
  /** Same drawing, moved or recoloured: applyOptions rather than recreate. */
  changed: string[];
  removed: string[];
}

export function diffAxisLevels(
  prev: ReadonlyMap<string, DrawingAxisLevel>,
  next: ReadonlyMap<string, DrawingAxisLevel>,
): AxisLevelDiff {
  const diff: AxisLevelDiff = { added: [], changed: [], removed: [] };
  for (const [id, level] of next) {
    const before = prev.get(id);
    if (!before) diff.added.push(id);
    else if (before.price !== level.price || before.color !== level.color) diff.changed.push(id);
  }
  for (const id of prev.keys()) if (!next.has(id)) diff.removed.push(id);
  return diff;
}
