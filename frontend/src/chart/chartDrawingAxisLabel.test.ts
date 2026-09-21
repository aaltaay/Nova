import { describe, expect, it } from 'vitest';
import type { SerializedDrawing } from 'lightweight-charts-drawing';
import {
  diffAxisLevels, drawingAxisLevels, drawingAxisLineOptions, type DrawingAxisLevel,
} from './chartDrawingAxisLabel';
import { CHART_DRAWING_OPTIONS, CHART_DRAWING_STYLE } from './chartDrawingConfig';

const drawing = (over: Partial<SerializedDrawing> = {}) => ({
  id: 'h1', type: 'horizontal-line', anchors: [{ price: 8.42, time: 1 }],
  style: { lineColor: '#3b82f6' }, ...over,
}) as unknown as SerializedDrawing;

describe('drawingAxisLevels', () => {
  it('takes the price level of horizontal and cross lines', () => {
    expect(drawingAxisLevels([drawing(), drawing({ id: 'x1', type: 'cross-line' })]))
      .toEqual(new Map([
        ['h1', { price: 8.42, color: '#3b82f6' }],
        ['x1', { price: 8.42, color: '#3b82f6' }],
      ]));
  });

  it('ignores drawings whose first anchor is not a price level', () => {
    for (const type of ['trend-line', 'vertical-line', 'ray', 'extended-line']) {
      expect(drawingAxisLevels([drawing({ type })]).size).toBe(0);
    }
  });

  it('skips a drawing with no usable price instead of charting NaN', () => {
    expect(drawingAxisLevels([drawing({ anchors: [] as never })]).size).toBe(0);
    expect(drawingAxisLevels([drawing({ anchors: [{ price: NaN, time: 1 }] as never })]).size).toBe(0);
    expect(drawingAxisLevels(null).size).toBe(0);
  });

  it('falls back to the default colour when a drawing carries none', () => {
    expect(drawingAxisLevels([drawing({ style: {} as never })]).get('h1')?.color)
      .toBe(CHART_DRAWING_STYLE.lineColor);
  });
});

describe('drawingAxisLineOptions', () => {
  it('carries the axis label and paints no second line over the drawing', () => {
    expect(drawingAxisLineOptions({ price: 8.42, color: '#ef4444' })).toMatchObject({
      price: 8.42, color: '#ef4444', axisLabelVisible: true, axisLabelColor: '#ef4444',
      lineVisible: false, title: '',
    });
  });
});

describe('diffAxisLevels', () => {
  const level = (price: number, color = '#3b82f6'): DrawingAxisLevel => ({ price, color });

  it('adds, updates in place, and removes', () => {
    const prev = new Map([['a', level(1)], ['b', level(2)], ['gone', level(3)]]);
    const next = new Map([['a', level(1)], ['b', level(9)], ['new', level(4)]]);
    expect(diffAxisLevels(prev, next)).toEqual({ added: ['new'], changed: ['b'], removed: ['gone'] });
  });

  it('treats a recolour as a change, and an identical level as no work', () => {
    expect(diffAxisLevels(new Map([['a', level(1)]]), new Map([['a', level(1, '#ef4444')]])).changed)
      .toEqual(['a']);
    expect(diffAxisLevels(new Map([['a', level(1)]]), new Map([['a', level(1)]])))
      .toEqual({ added: [], changed: [], removed: [] });
  });
});

describe('the clipped in-plot label', () => {
  it('stays off, which is what the axis chip replaces', () => {
    expect(CHART_DRAWING_OPTIONS.showPrice).toBe(false);
  });
});
