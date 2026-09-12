/** Chart pan/scale while a drawing tool is armed (D-010) or a handle is dragged (#119).

 * Placement lives in `chartDrawingPlace` (container pointerup). Lightweight
 * Charts still treats a click-drag as time-scale pan, so disable pressed-mouse
 * pan/scale and kinetic fling while a tool is armed or a selected handle is
 * being edited. Wheel zoom stays on. Idle + not editing restores pan.
 */

export function chartPanLocked(
  activeTool: string | null,
  editingHandle = false,
): boolean {
  return Boolean(activeTool) || editingHandle;
}

export function chartInteractionForTool(
  activeTool: string | null,
  editingHandle = false,
): {
  handleScroll: {
    mouseWheel: boolean;
    pressedMouseMove: boolean;
    horzTouchDrag: boolean;
    vertTouchDrag: boolean;
  };
  handleScale: {
    axisPressedMouseMove: boolean;
    mouseWheel: boolean;
    pinch: boolean;
  };
  kineticScroll: {
    mouse: boolean;
    touch: boolean;
  };
} {
  const drawing = chartPanLocked(activeTool, editingHandle);
  return {
    handleScroll: {
      mouseWheel: true,
      pressedMouseMove: !drawing,
      horzTouchDrag: !drawing,
      vertTouchDrag: !drawing,
    },
    handleScale: {
      axisPressedMouseMove: !drawing,
      mouseWheel: true,
      pinch: true,
    },
    kineticScroll: {
      mouse: false,
      touch: !drawing,
    },
  };
}

export function applyChartHostInteraction(
  host: HTMLElement | null,
  chart: { applyOptions: (opts: ReturnType<typeof chartInteractionForTool>) => void } | null,
  activeTool: string | null,
  editingHandle: boolean,
): void {
  chart?.applyOptions(chartInteractionForTool(activeTool, editingHandle));
  if (!host) return;
  host.dataset.chartPanLocked = chartPanLocked(activeTool, editingHandle) ? '1' : '';
  host.dataset.editingHandle = editingHandle ? '1' : '';
}
