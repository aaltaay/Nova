/**
 * Place the Nth Trader window on the Nth display (cascade if more windows
 * than monitors). Pure -- Electron and tests share this math.
 */
export type DisplayBounds = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export type WindowBounds = {
  x: number;
  y: number;
  width: number;
  height: number;
};

const EDGE_PAD = 24;
const CASCADE = 36;

export function boundsForTraderWindow(
  displays: DisplayBounds[],
  index: number,
  width: number,
  height: number,
): WindowBounds {
  if (displays.length === 0) {
    return { x: EDGE_PAD + index * CASCADE, y: EDGE_PAD + index * CASCADE, width, height };
  }
  const sorted = [...displays].sort((a, b) => a.x - b.x || a.y - b.y);
  const slot = Math.min(Math.max(index, 0), sorted.length - 1);
  const extra = Math.max(0, index - slot);
  const d = sorted[slot];
  const w = Math.min(width, Math.max(640, d.width - EDGE_PAD * 2));
  const h = Math.min(height, Math.max(480, d.height - EDGE_PAD * 2));
  return {
    x: d.x + EDGE_PAD + extra * CASCADE,
    y: d.y + EDGE_PAD + extra * CASCADE,
    width: w,
    height: h,
  };
}
