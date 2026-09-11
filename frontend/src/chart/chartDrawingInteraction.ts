/** Chart pan/scale while a drawing tool is armed (D-010).

 * Placement lives in `chartDrawingPlace` (container pointerup). Lightweight
 * Charts still treats a click-drag as time-scale pan, so disable pressed-mouse
 * pan/scale and kinetic fling while a tool is armed. Wheel zoom stays on.
 */

export function chartInteractionForTool(activeTool: string | null): {
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
  const drawing = Boolean(activeTool);
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
