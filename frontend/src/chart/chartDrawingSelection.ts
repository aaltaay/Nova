/** The selected drawing's id and color. No store, so a recorded pane can read it. */

import type { IDrawing } from 'lightweight-charts-drawing';
import { CHART_DRAWING_STYLE } from './chartDrawingConfig';

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
