/** Handle-edit hit test and pan lock (issue #119).

 * `lightweight-charts-drawing` already moves a selected anchor on mousedown.
 * Lightweight Charts still treats that same press as time-scale pan unless
 * `pressedMouseMove` is off. Lock pan only for the handle gesture -- not for
 * a selected-but-idle drawing, and not instead of D-010 tool-armed lock.
 */

import { pointerPointInElement, type ChartPlacePoint } from './chartDrawingPlace';

export interface ChartHandleHitManager {
  getSelectedDrawing: () => { id: string } | null;
  hitTestAnchor: (point: ChartPlacePoint) => number | null;
}

export function handlePointFromPointer(
  container: Pick<HTMLElement, 'getBoundingClientRect'>,
  clientX: number,
  clientY: number,
): ChartPlacePoint {
  // Same space as the library's getPointFromEvent (container box, not LWC host).
  return pointerPointInElement(container, clientX, clientY);
}

export function pointerHitsSelectedHandle(
  manager: ChartHandleHitManager | null,
  point: ChartPlacePoint,
): boolean {
  if (!manager || !manager.getSelectedDrawing()) return false;
  return manager.hitTestAnchor(point) !== null;
}

export function bindHandleEditPointer(
  container: HTMLElement,
  getManager: () => ChartHandleHitManager | null,
  isArmed: () => boolean,
  onEditingChange: (editing: boolean) => void,
): () => void {
  let editing = false;

  const endEdit = (event: PointerEvent) => {
    if (!editing || event.button !== 0) return;
    editing = false;
    try {
      if (container.hasPointerCapture(event.pointerId)) {
        container.releasePointerCapture(event.pointerId);
      }
    } catch {
      // jsdom / detached nodes.
    }
    onEditingChange(false);
  };

  const onDown = (event: PointerEvent) => {
    if (isArmed() || event.button !== 0) return;
    const point = handlePointFromPointer(container, event.clientX, event.clientY);
    if (!pointerHitsSelectedHandle(getManager(), point)) return;
    editing = true;
    try {
      container.setPointerCapture(event.pointerId);
    } catch {
      // Capture is optional -- jsdom and some detached nodes throw.
    }
    onEditingChange(true);
  };

  container.addEventListener('pointerdown', onDown, true);
  container.addEventListener('pointerup', endEdit, true);
  container.addEventListener('pointercancel', endEdit, true);
  return () => {
    container.removeEventListener('pointerdown', onDown, true);
    container.removeEventListener('pointerup', endEdit, true);
    container.removeEventListener('pointercancel', endEdit, true);
  };
}
