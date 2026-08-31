import { describe, expect, it } from 'vitest';
import type { Time } from 'lightweight-charts';
import type { SerializedDrawing } from 'lightweight-charts-drawing';
import { drawingFactory, shouldHydrateDrawings, snapAll } from './chartDrawingHydrate';
import { buildSeriesTimeIndex } from './chartDrawingTime';

const AT = { symbol: 'AAPL', revision: 3, hadBars: true } as const;

describe('shouldHydrateDrawings', () => {
  it('hydrates on the very first pass', () => {
    expect(shouldHydrateDrawings(null, { symbol: 'AAPL', revision: 0, hasBars: false })).toBe(true);
  });

  it('hydrates on a symbol switch so levels never bleed across tickers', () => {
    expect(shouldHydrateDrawings(AT, { symbol: 'TSLA', revision: 3, hasBars: true })).toBe(true);
  });

  it('hydrates when a sibling pane changed the stored set', () => {
    expect(shouldHydrateDrawings(AT, { symbol: 'AAPL', revision: 4, hasBars: true })).toBe(true);
  });

  it('hydrates once bars finally arrive so anchors can snap', () => {
    expect(
      shouldHydrateDrawings(
        { symbol: 'AAPL', revision: 3, hadBars: false },
        { symbol: 'AAPL', revision: 3, hasBars: true },
      ),
    ).toBe(true);
  });

  it('skips our own echo -- rebuilding would drop the held selection', () => {
    expect(shouldHydrateDrawings(AT, { symbol: 'AAPL', revision: 3, hasBars: true })).toBe(false);
  });

  it('skips when the pane still has no bars', () => {
    expect(
      shouldHydrateDrawings(
        { symbol: 'AAPL', revision: 3, hadBars: false },
        { symbol: 'AAPL', revision: 3, hasBars: false },
      ),
    ).toBe(false);
  });
});

describe('drawingFactory', () => {
  const stored = {
    id: 'horizontal-line-1',
    type: 'horizontal-line',
    anchors: [{ time: 1_756_000_000 as Time, price: 231.5 }],
    style: { lineColor: '#3b82f6', lineWidth: 1 },
    options: {},
  } as SerializedDrawing;

  it('rebuilds a stored horizontal line into a live drawing', () => {
    const drawing = drawingFactory('horizontal-line', stored);
    expect(drawing?.id).toBe('horizontal-line-1');
    expect(drawing?.type).toBe('horizontal-line');
    expect(drawing?.anchors[0].price).toBe(231.5);
  });

  it('rebuilds a trend line with both anchors', () => {
    const trend = {
      ...stored,
      id: 'trendline-1',
      type: 'trend-line',
      anchors: [
        { time: 1_756_000_000 as Time, price: 10 },
        { time: 1_756_003_600 as Time, price: 12 },
      ],
    } as SerializedDrawing;
    expect(drawingFactory('trend-line', trend)?.anchors).toHaveLength(2);
  });

  it.each([
    ['ray', 2],
    ['extended-line', 2],
    ['horizontal-ray', 1],
  ])('rebuilds a stored %s', (type, anchorCount) => {
    const drawing = {
      ...stored,
      id: `${type}-1`,
      type,
      anchors: [
        { time: 1_756_000_000 as Time, price: 10 },
        { time: 1_756_003_600 as Time, price: 12 },
      ].slice(0, anchorCount),
    } as SerializedDrawing;
    expect(drawingFactory(type, drawing)?.type).toBe(type);
  });

  it('returns null for a tool type the library does not know', () => {
    expect(drawingFactory('not-a-real-tool', stored)).toBeNull();
  });
});

describe('snapAll', () => {
  it('snaps every stored drawing onto the pane grid', () => {
    const index = buildSeriesTimeIndex(['2026-08-25', '2026-08-26'] as Time[]);
    const stored = [
      {
        id: 'a',
        type: 'vertical-line',
        anchors: [{ time: Math.floor(Date.UTC(2026, 7, 26, 9, 30) / 1000) as Time, price: 1 }],
        style: {},
        options: {},
      },
    ] as SerializedDrawing[];
    expect(snapAll(stored, index)[0].anchors[0].time).toBe('2026-08-26');
  });
});
