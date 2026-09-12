/** Color change for a selected chart drawing (issue #121). */
import type { IDrawing } from 'lightweight-charts-drawing';
import { CHART_DRAWING_STYLE } from './chartDrawingConfig';
import { toStorableDrawing } from './chartDrawingTime';
import { upsertDrawing } from './chartDrawingsStore';

export interface DrawingSelectionState {
  id: string;
  color: string;
}

export function selectionStateFromDrawing(
  drawing: IDrawing | null | undefined,
): DrawingSelectionState | null {
  if (!drawing) return null;
  const json = drawing.toJSON();
  return { id: json.id, color: json.style?.lineColor ?? CHART_DRAWING_STYLE.lineColor };
}

/**
 * Apply a new `lineColor` to a live drawing, persist it via the store, and
 * return the updated selection state.
 */
export function applyDrawingColor(
  drawing: IDrawing,
  color: string,
  symbol: string,
  persist: (mutate: () => void) => void,
): DrawingSelectionState {
  drawing.updateStyle({ lineColor: color });
  const storable = toStorableDrawing(drawing.toJSON());
  if (storable) {
    persist(() => upsertDrawing(symbol, storable));
  }
  return { id: drawing.toJSON().id, color };
}
