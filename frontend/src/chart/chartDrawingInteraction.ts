/** Chart pan/scale while a drawing tool is armed (D-010).

 * Trend Line / Ray / Extended Line collect two clicks via subscribeClick.
 * Lightweight Charts still treats a click-drag as time-scale pan, so the
 * first click never lands as an anchor. Disable pressed-mouse pan/scale
 * while a tool is armed; wheel zoom stays on. This is not a new click
 * protocol -- it only stops the chart from eating the existing one.
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
  };
}
