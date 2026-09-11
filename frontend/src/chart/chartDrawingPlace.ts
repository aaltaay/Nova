/** Two-click / one-click placement for armed chart tools (D-010).

 * `lightweight-charts-drawing` has no native click-to-place: `setActiveTool`
 * only stores the name, and its `subscribeClick` handler is a no-op while a
 * tool is armed. Lightweight Charts also cancels `subscribeClick` once the
 * pointer moves 5px -- even after pan is disabled -- so Nova places from the
 * chart container's pointerup. Same two-click contract (A, then B). Not a
 * third "ready to draw" protocol.
 */

export interface ChartPlaceAnchor {
  time: unknown;
  price: number;
}

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
    onPoint(pointerPointInElement(container, event.clientX, event.clientY));
  };
  container.addEventListener('pointerdown', onDown);
  container.addEventListener('pointerup', onUp);
  return () => {
    container.removeEventListener('pointerdown', onDown);
    container.removeEventListener('pointerup', onUp);
  };
}
