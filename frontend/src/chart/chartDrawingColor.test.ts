import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Time } from 'lightweight-charts';
import type { SerializedDrawing } from 'lightweight-charts-drawing';
import {
  applyDrawingColor,
  selectionStateFromDrawing,
} from './chartDrawingColor';
import { CHART_DRAWING_STYLE } from './chartDrawingConfig';
import { clearDrawingsStoreForTests, getDrawings, upsertDrawing } from './chartDrawingsStore';

function makeFakeDrawing(id: string, color: string): {
  toJSON: () => SerializedDrawing;
  updateStyle: ReturnType<typeof vi.fn>;
} {
  let style = { lineColor: color, lineWidth: 1 };
  const drawing = {
    updateStyle: vi.fn((partial: Partial<typeof style>) => {
      style = { ...style, ...partial };
    }),
    toJSON: () => ({
      id,
      type: 'TrendLine',
      anchors: [
        { time: 1_756_000_000 as Time, price: 100 },
        { time: 1_756_001_000 as Time, price: 110 },
      ],
      style: { ...style },
      options: {},
    }),
  };
  return drawing;
}

beforeEach(() => {
  vi.useFakeTimers();
  clearDrawingsStoreForTests();
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: true, status: 200, json: async () => ({ drawings: [] }),
  })));
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('selectionStateFromDrawing', () => {
  it('returns null for a null drawing', () => {
    expect(selectionStateFromDrawing(null)).toBeNull();
    expect(selectionStateFromDrawing(undefined)).toBeNull();
  });

  it('extracts the id and current lineColor', () => {
    const drawing = makeFakeDrawing('tl-1', '#ef4444');
    const state = selectionStateFromDrawing(drawing as never);
    expect(state).toEqual({ id: 'tl-1', color: '#ef4444' });
  });

  it('falls back to the default color when style has no lineColor', () => {
    const drawing = makeFakeDrawing('tl-2', '#3b82f6');
    // Simulate a drawing whose serialized style lacks lineColor.
    const orig = drawing.toJSON;
    drawing.toJSON = () => {
      const json = orig();
      return { ...json, style: {} as typeof json.style };
    };
    const state = selectionStateFromDrawing(drawing as never);
    expect(state?.color).toBe(CHART_DRAWING_STYLE.lineColor);
  });
});

describe('applyDrawingColor', () => {
  it('calls updateStyle with the new lineColor', () => {
    const drawing = makeFakeDrawing('tl-1', '#3b82f6');
    const persist = vi.fn((fn: () => void) => fn());

    applyDrawingColor(drawing as never, '#ef4444', 'AAPL', persist);

    expect(drawing.updateStyle).toHaveBeenCalledWith({ lineColor: '#ef4444' });
  });

  it('persists the drawing to the store via the persist callback', () => {
    const drawing = makeFakeDrawing('tl-1', '#3b82f6');
    const persist = vi.fn((fn: () => void) => fn());

    applyDrawingColor(drawing as never, '#22c55e', 'AAPL', persist);

    expect(persist).toHaveBeenCalledOnce();
    const stored = getDrawings('AAPL');
    expect(stored).toHaveLength(1);
    expect(stored[0].style.lineColor).toBe('#22c55e');
  });

  it('returns updated selection state', () => {
    const drawing = makeFakeDrawing('tl-1', '#3b82f6');
    const persist = vi.fn((fn: () => void) => fn());

    const result = applyDrawingColor(drawing as never, '#a855f7', 'AAPL', persist);

    expect(result).toEqual({ id: 'tl-1', color: '#a855f7' });
  });

  it('uses the upsertDrawing path so debounced save kicks in', () => {
    upsertDrawing('AAPL', {
      id: 'tl-1',
      type: 'TrendLine',
      anchors: [
        { time: 1_756_000_000 as Time, price: 100 },
        { time: 1_756_001_000 as Time, price: 110 },
      ],
      style: { lineColor: '#3b82f6', lineWidth: 1 },
      options: {},
    } as SerializedDrawing);

    const drawing = makeFakeDrawing('tl-1', '#3b82f6');
    const persist = vi.fn((fn: () => void) => fn());
    applyDrawingColor(drawing as never, '#ef4444', 'AAPL', persist);

    const stored = getDrawings('AAPL');
    expect(stored).toHaveLength(1);
    expect(stored[0].style.lineColor).toBe('#ef4444');
  });
});
