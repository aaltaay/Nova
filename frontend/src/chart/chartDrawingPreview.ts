/** Two-click rubber-band preview after point A (issue #119).

 * `lightweight-charts-drawing` `setActiveTool` does not place or preview.
 * Nova already collects A then B via `placeArmedToolClick`. After A, attach
 * the same TrendLine / ExtendedLine / Ray class as a series primitive and
 * move its second anchor on pointermove. Do not `addDrawing` the preview --
 * that would persist and disarm the tool.
 */

import type { Anchor, IDrawing } from 'lightweight-charts-drawing';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';
import { CHART_DRAWING_OPTIONS, CHART_DRAWING_STYLE, CHART_TWO_ANCHOR_TOOLS } from './chartDrawingConfig';
import { placePointFromPointer, type ChartPlacePoint } from './chartDrawingPlace';

export const CHART_PLACE_PREVIEW_ID = 'nova-place-preview';

export function shouldShowPlacePreview(
  tool: string | null,
  pending: Anchor | null,
): boolean {
  return Boolean(tool && pending && CHART_TWO_ANCHOR_TOOLS[tool]);
}

export function createPlacePreviewDrawing(
  tool: string,
  start: Anchor,
  cursor: Anchor,
): IDrawing | null {
  const DrawingClass = CHART_TWO_ANCHOR_TOOLS[tool];
  if (!DrawingClass) return null;
  return new DrawingClass(CHART_PLACE_PREVIEW_ID, [start, cursor], CHART_DRAWING_STYLE, CHART_DRAWING_OPTIONS);
}

export function attachPlacePreview(
  drawing: IDrawing,
  series: ISeriesApi<'Candlestick'>,
  chart: IChartApi,
  container: HTMLElement,
): void {
  drawing.attach(series, chart, container);
}

export function movePlacePreview(drawing: IDrawing, cursor: Anchor): void {
  drawing.updateAnchor(1, cursor);
}

export function detachPlacePreview(drawing: IDrawing | null | undefined): void {
  if (!drawing) return;
  try {
    if (drawing.isAttached()) drawing.detach();
  } catch {
    // Detach is best-effort -- a torn-down series should not break cleanup.
  }
}

export function markPlacePreviewHost(host: HTMLElement | null, previewing: boolean): void {
  if (!host) return;
  host.dataset.drawingPreview = previewing ? '1' : '';
  host.dataset.placePending = previewing ? '1' : '';
}

export function bindPlacePreviewPointer(
  container: HTMLElement,
  isPreviewing: () => boolean,
  onPoint: (point: ChartPlacePoint) => void,
): () => void {
  const onMove = (event: PointerEvent) => {
    if (!isPreviewing()) return;
    onPoint(placePointFromPointer(container, event.clientX, event.clientY));
  };
  container.addEventListener('pointermove', onMove, true);
  return () => container.removeEventListener('pointermove', onMove, true);
}
