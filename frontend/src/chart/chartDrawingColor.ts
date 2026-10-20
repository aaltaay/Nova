/** Color change for a selected chart drawing (issue #121). */
import type { IDrawing } from 'lightweight-charts-drawing';
import { toStorableDrawing } from './chartDrawingTime';
import { upsertDrawing } from './chartDrawingsStore';
import {
  selectionStateFromDrawing,
  type DrawingSelectionState,
} from './chartDrawingSelection';

export { selectionStateFromDrawing, type DrawingSelectionState };

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
