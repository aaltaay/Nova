import { describe, expect, it, vi } from 'vitest';
import { emptyPx, LineRenderer, type Px } from './sceneRender';
import type { LabelRect } from './sceneLabels';

/** A canvas that draws nothing and measures six pixels a character: enough to place labels. */
function fakeCtx() {
  const calls: string[] = [];
  const ctx = new Proxy({} as Record<string, unknown>, {
    get(target, key: string) {
      if (key === 'measureText') return (text: string) => ({ width: text.length * 6 });
      if (key in target) return target[key];
      return (...args: unknown[]) => {
        calls.push(`${key}:${args.join(',')}`);
      };
    },
    set(target, key: string, value) {
      target[key] = value;
      return true;
    },
  });
  return { ctx: ctx as unknown as CanvasRenderingContext2D, calls };
}

function paint(px: Px, width = 600, height = 400) {
  const { ctx } = fakeCtx();
  const words: LabelRect[][] = [];
  const renderer = new LineRenderer(px, () => {}, rects => words.push(rects));
  renderer.draw({
    useMediaCoordinateSpace: (draw: (scope: unknown) => void) => draw({ context: ctx, mediaSize: { width, height } }),
  } as never);
  return words;
}

const BOX = {
  t1: 1 as never, t2: 2 as never, p1: 5.6, p2: 4.5, fill: 'rgba(0,0,0,0.1)', stroke: '#4aa3ff', dashed: false,
  label: '5m first pullback · leg +83.3%', labelColor: '#4aa3ff',
};

describe('LineRenderer', () => {
  it('publishes every label it drew, so what floats over a candle can keep clear of them', () => {
    const px: Px = { ...emptyPx(), boxes: [{ x1: 100, x2: 160, y1: 120, y2: 350, b: BOX }] };
    const [rects] = paint(px);
    // The box's label starts at the left edge of the box, nine pixels over its top, 14 tall and wide as its text.
    const label = rects.find(r => Math.abs(r.left - 100) < 1);
    expect(label).toBeDefined();
    expect(label!.bottom - label!.top).toBe(14);
    expect(label!.right - label!.left).toBeGreaterThan(100);
    expect(label!.top).toBe(120 - 9 - 7);
  });

  it('publishes the pins and the fixed labels too', () => {
    const px: Px = {
      ...emptyPx(),
      pins: [{ x: 300, y: 200, p: { t: 1 as never, price: 5, label: 'ENTER NOW', color: '#22c55e' } }],
      segments: [{ x1: 40, y: 260, s: { t1: null, price: 5, color: '#aaa', dashed: true, label: 'ENTRY 5.00' } }],
    };
    const [rects] = paint(px);
    expect(rects).toHaveLength(2);
    expect(rects.some(r => r.left <= 300 && r.right >= 300 && r.bottom < 200)).toBe(true);
    expect(rects.some(r => Math.abs(r.left - 44) < 1 && r.top === 260 - 8 - 7)).toBe(true);
  });

  it('publishes an empty list when the pane has no words', () => {
    const onWords = vi.fn();
    const { ctx } = fakeCtx();
    new LineRenderer(emptyPx(), () => {}, onWords).draw({
      useMediaCoordinateSpace: (draw: (scope: unknown) => void) =>
        draw({ context: ctx, mediaSize: { width: 600, height: 400 } }),
    } as never);
    expect(onWords).toHaveBeenCalledWith([]);
  });
});
