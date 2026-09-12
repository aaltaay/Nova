/** Two-click / one-click placement for armed chart tools (D-010).

 * `lightweight-charts-drawing` has no native click-to-place: `setActiveTool`
 * only stores the name, and its `subscribeClick` handler is a no-op while a
 * tool is armed. Lightweight Charts also cancels `subscribeClick` once the
 * pointer moves 5px -- even after pan is disabled -- so Nova places from the
 * chart container's pointerup. Same two-click contract (A, then B). Not a
 * third "ready to draw" protocol.
 */

import type { Anchor } from 'lightweight-charts-drawing';

export type ChartPlaceAnchor = Anchor;

export interface ChartPlacePoint {
  x: number;
  y: number;
}

export type ChartPlaceResult =
  | { action: 'ignore'; pending: ChartPlaceAnchor | null }
  | { action: 'wait'; pending: ChartPlaceAnchor }
  | { action: 'one'; pending: null; anchors: [ChartPlaceAnchor] }
  | { action: 'two'; pending: null; anchors: [ChartPlaceAnchor, ChartPlaceAnchor] };

export function pointerPointInElement(
  el: Pick<HTMLElement, 'getBoundingClientRect'>,
  clientX: number,
  clientY: number,
): ChartPlacePoint {
  const rect = el.getBoundingClientRect();
  return { x: clientX - rect.left, y: clientY - rect.top };
}

/** Prefer the LWC host so axis/gap chrome on `.chart-body` does not shift anchors. */
export function placePointFromPointer(
  container: HTMLElement,
  clientX: number,
  clientY: number,
): ChartPlacePoint {
  const plot = container.querySelector<HTMLElement>('.tv-lightweight-charts') ?? container;
  return pointerPointInElement(plot, clientX, clientY);
}

export function placeArmedToolClick(input: {
  tool: string | null;
  pending: ChartPlaceAnchor | null;
  anchor: ChartPlaceAnchor;
  twoAnchorTool: boolean;
  singleAnchorTool: boolean;
}): ChartPlaceResult {
  const { tool, pending, anchor, twoAnchorTool, singleAnchorTool } = input;
  if (!tool) return { action: 'ignore', pending };
  if (twoAnchorTool) {
    if (!pending) return { action: 'wait', pending: anchor };
    return { action: 'two', pending: null, anchors: [pending, anchor] };
  }
  if (singleAnchorTool) {
    return { action: 'one', pending: null, anchors: [anchor] };
  }
  return { action: 'ignore', pending };
}

export function bindArmedToolPointer(
  container: HTMLElement,
  isArmed: () => boolean,
  onPoint: (point: ChartPlacePoint) => void,
): () => void {
  const onDown = (event: PointerEvent) => {
    if (!isArmed() || event.button !== 0) return;
    try {
      container.setPointerCapture(event.pointerId);
    } catch {
      // Capture is optional -- jsdom and some detached nodes throw.
    }
  };
  const onUp = (event: PointerEvent) => {
    if (!isArmed() || event.button !== 0) return;
    try {
      if (container.hasPointerCapture(event.pointerId)) {
        container.releasePointerCapture(event.pointerId);
      }
    } catch {
      // Same as capture -- ignore if the platform cannot track it.
    }
    onPoint(placePointFromPointer(container, event.clientX, event.clientY));
  };
  // Capture beats Lightweight Charts canvas handlers that stop bubble.
  container.addEventListener('pointerdown', onDown, true);
  container.addEventListener('pointerup', onUp, true);
  return () => {
    container.removeEventListener('pointerdown', onDown, true);
    container.removeEventListener('pointerup', onUp, true);
  };
}
