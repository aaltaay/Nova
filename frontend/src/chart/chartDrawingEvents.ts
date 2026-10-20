/**
 * DrawingManager placement dispatch, event subscriptions, and keyboard bindings.
 *
 * Extracted from `useChartDrawingManager.ts` so the React hook stays focused
 * on lifecycle/store hydration and both modules remain well under 400 lines.
 */

import type { Anchor, DrawingManager, IDrawing } from 'lightweight-charts-drawing';
import {
  CHART_DRAWING_OPTIONS,
  CHART_DRAWING_STYLE,
  CHART_SINGLE_ANCHOR_TOOLS,
  CHART_TWO_ANCHOR_TOOLS,
} from './chartDrawingConfig';
import {
  selectionStateFromDrawing,
  type DrawingSelectionState,
} from './chartDrawingSelection';
import { shouldDisarmToolOnDrawingAdded } from './chartDrawingHydrate';
import {
  deleteSelectedDrawingOnKey,
  ownsChartDrawingHotkeyFocus,
  releaseChartDrawingHotkeyFocus,
  resolveChartDrawingHotkey,
} from './chartDrawingKeys';
import { placeArmedToolClick } from './chartDrawingPlace';

export interface PlaceDrawingAtAnchorOptions {
  tool: string;
  anchor: Anchor;
  pendingAnchorRef: { current: Anchor | null };
  manager: DrawingManager;
  host: HTMLDivElement | null;
  startOrMovePreview: (start: Anchor, cursor: Anchor) => void;
  clearPlacePreview: () => void;
}

export function placeDrawingAtAnchor({
  tool,
  anchor,
  pendingAnchorRef,
  manager,
  host,
  startOrMovePreview,
  clearPlacePreview,
}: PlaceDrawingAtAnchorOptions): void {
  const result = placeArmedToolClick({
    tool,
    pending: pendingAnchorRef.current,
    anchor,
    twoAnchorTool: Boolean(CHART_TWO_ANCHOR_TOOLS[tool]),
    singleAnchorTool: Boolean(CHART_SINGLE_ANCHOR_TOOLS[tool]),
  });
  pendingAnchorRef.current = result.pending;
  if (result.action === 'wait') {
    startOrMovePreview(anchor, anchor);
  } else if (result.action === 'two') {
    clearPlacePreview();
    const DrawingClass = CHART_TWO_ANCHOR_TOOLS[tool];
    if (!DrawingClass) return;
    manager.addDrawing(
      new DrawingClass(
        `${tool.toLowerCase()}-${Date.now()}`,
        result.anchors,
        CHART_DRAWING_STYLE,
        CHART_DRAWING_OPTIONS,
      ),
    );
  } else if (result.action === 'one') {
    clearPlacePreview();
    const DrawingClass = CHART_SINGLE_ANCHOR_TOOLS[tool];
    if (!DrawingClass) return;
    manager.addDrawing(
      new DrawingClass(
        `${tool.toLowerCase()}-${Date.now()}`,
        result.anchors,
        CHART_DRAWING_STYLE,
        CHART_DRAWING_OPTIONS,
      ),
    );
  }
  if (host) host.dataset.drawingCount = String(manager.getAllDrawings().length);
}

export interface BindDrawingManagerEventsOptions {
  manager: DrawingManager;
  managerRef: { current: DrawingManager | null };
  applyingRef: { current: boolean };
  symbolRef: { current: string };
  hotkeyOwner: symbol;
  setActiveTool: (next: string | null) => void;
  setSelection: (next: DrawingSelectionState | null) => void;
  storeDrawing: (drawing: IDrawing | undefined) => void;
  persist: (mutate: () => void) => void;
  removeDrawing: (symbolKey: string, drawingId: string) => void;
}

export function bindDrawingManagerEvents({
  manager,
  managerRef,
  applyingRef,
  symbolRef,
  hotkeyOwner,
  setActiveTool,
  setSelection,
  storeDrawing,
  persist,
  removeDrawing,
}: BindDrawingManagerEventsOptions): () => void {
  const unsubAdded = manager.on('drawing:added', (event) => {
    if (shouldDisarmToolOnDrawingAdded(applyingRef.current)) {
      setActiveTool(null);
    }
    storeDrawing(event.drawing);
  });
  // Fires per mousemove while dragging an anchor; the store debounces the PUT.
  const unsubUpdated = manager.on('drawing:updated', (event) => {
    storeDrawing(event.drawing);
  });
  const unsubRemoved = manager.on('drawing:removed', (event) => {
    const id = event.drawingId;
    if (applyingRef.current || !id) return;
    persist(() => removeDrawing(symbolRef.current, id));
  });
  const unsubSelected = manager.on('drawing:selected', (event) => {
    setSelection(selectionStateFromDrawing(event.drawing));
  });
  const unsubDeselected = manager.on('drawing:deselected', () => {
    setSelection(null);
  });

  const onDeleteKey = (event: KeyboardEvent) => {
    const current = managerRef.current;
    if (!current) return;
    if (deleteSelectedDrawingOnKey(current, event)) return;
    if (!ownsChartDrawingHotkeyFocus(hotkeyOwner)) return;
    const tool = resolveChartDrawingHotkey(event);
    if (!tool) return;
    event.preventDefault();
    setActiveTool(tool);
  };
  window.addEventListener('keydown', onDeleteKey);
  return () => {
    unsubAdded();
    unsubUpdated();
    unsubRemoved();
    unsubSelected();
    unsubDeselected();
    window.removeEventListener('keydown', onDeleteKey);
    releaseChartDrawingHotkeyFocus(hotkeyOwner);
  };
}
