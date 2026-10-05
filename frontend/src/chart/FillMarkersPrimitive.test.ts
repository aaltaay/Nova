import type { IChartApi, SeriesAttachedParameter, SeriesMarker, SeriesType, Time } from 'lightweight-charts';
import { describe, expect, it, vi } from 'vitest';
import { FillMarkersPrimitive, layoutFillMarkers, markerHeight, markerMargin } from './FillMarkersPrimitive';
import { paneWords } from './paneWords';

const T1 = 1_000 as Time;
const T2 = 1_060 as Time;

const BUY: SeriesMarker<Time> = {
  time: T1, position: 'belowBar', shape: 'arrowUp', color: 'green', text: '$2.76', size: 1, id: 'fill-1',
};
const SELL: SeriesMarker<Time> = {
  time: T2, position: 'aboveBar', shape: 'arrowDown', color: 'red', text: '$3.10', size: 1, id: 'fill-2',
};

const BARS = new Map<Time, { high: number; low: number }>([[T1, { high: 3, low: 2.5 }], [T2, { high: 3.2, low: 2.9 }]]);

function attach() {
  const requestUpdate = vi.fn();
  const subscribeDataChanged = vi.fn();
  const series = {
    subscribeDataChanged,
    dataByIndex: (i: number) => [...BARS.values()][i] ?? null,
    priceToCoordinate: (price: number) => 1000 - price * 100,
  };
  const chart = {
    options: () => ({ layout: { fontSize: 12, fontFamily: 'Inter' } }),
    timeScale: () => ({
      timeToCoordinate: (t: Time) => (t === T1 ? 100 : t === T2 ? 108 : null),
      timeToIndex: (t: Time) => {
        const i = [...BARS.keys()].indexOf(t);
        return i < 0 ? null : i;
      },
      options: () => ({ barSpacing: 8 }),
    }),
  };
  const primitive = new FillMarkersPrimitive();
  primitive.attached({ chart, series, requestUpdate } as unknown as SeriesAttachedParameter<Time, SeriesType>);
  return { primitive, requestUpdate, subscribeDataChanged, chart: chart as unknown as IChartApi };
}

/** Paint the arrows once on a fake canvas, as lightweight-charts would. */
function paint(primitive: FillMarkersPrimitive) {
  const ctx = {
    beginPath: vi.fn(), moveTo: vi.fn(), lineTo: vi.fn(), fill: vi.fn(), fillText: vi.fn(),
    measureText: (text: string) => ({ width: text.length * 6 }),
    font: '', fillStyle: '', textAlign: '', textBaseline: '',
  };
  const target = {
    useBitmapCoordinateSpace: (draw: (scope: unknown) => void) =>
      draw({ context: ctx, horizontalPixelRatio: 1, verticalPixelRatio: 1 }),
    useMediaCoordinateSpace: (draw: (scope: unknown) => void) => draw({ context: ctx }),
  };
  primitive.paneViews()[0].renderer()?.draw(target as never);
}

describe('FillMarkersPrimitive', () => {
  it('never listens to the series data: a tick needs no redraw of its own', () => {
    const { primitive, subscribeDataChanged, requestUpdate } = attach();
    primitive.setMarkers([BUY]);
    expect(subscribeDataChanged).not.toHaveBeenCalled();
    expect(requestUpdate).toHaveBeenCalledTimes(1);
  });

  it('redraws only when the fills change', () => {
    const { primitive, requestUpdate } = attach();
    expect(requestUpdate).not.toHaveBeenCalled(); // nothing to draw yet
    primitive.setMarkers([]);
    expect(requestUpdate).not.toHaveBeenCalled();
    primitive.setMarkers([BUY]);
    primitive.setMarkers([{ ...BUY }]);
    expect(requestUpdate).toHaveBeenCalledTimes(1);
    primitive.setMarkers([BUY, SELL]);
    expect(requestUpdate).toHaveBeenCalledTimes(2);
    primitive.setMarkers([]);
    expect(requestUpdate).toHaveBeenCalledTimes(3);
  });

  it('places a buy under its bar and a sell over it', () => {
    const { primitive } = attach();
    primitive.setMarkers([BUY, SELL]);
    primitive.updateAllViews();
    const [buy, sell] = primitive.px;
    const size = markerHeight(8, 1);
    const margin = markerMargin(8);
    expect(buy).toMatchObject({ x: 100, up: true, color: 'green', text: '$2.76', size });
    expect(buy.y).toBe(1000 - 2.5 * 100 + size / 2 + margin);
    expect(buy.textY).toBeGreaterThan(buy.y);
    expect(sell).toMatchObject({ x: 108, up: false, color: 'red' });
    expect(sell.y).toBe(1000 - 3.2 * 100 - size / 2 - margin);
    expect(sell.textY).toBeLessThan(sell.y);
  });

  it('stacks a second fill on the same bar past the first', () => {
    const second = { ...BUY, id: 'fill-3', text: '$2.80' };
    const px = layoutFillMarkers([BUY, second], {
      x: () => 50,
      bar: () => ({ high: 3, low: 2.5 }),
      y: p => 1000 - p * 100,
      barSpacing: 8,
      textHeight: 12,
    });
    expect(px).toHaveLength(2);
    expect(px[1].y).toBeGreaterThan(px[0].textY);
  });

  it('skips a fill whose bar is not on the series and draws nothing once detached', () => {
    const { primitive } = attach();
    primitive.setMarkers([{ ...BUY, time: 999 as Time }]);
    primitive.updateAllViews();
    expect(primitive.px).toEqual([]);
    primitive.setMarkers([BUY]);
    primitive.detached();
    primitive.updateAllViews();
    expect(primitive.px).toEqual([]);
  });

  it('keeps room over and under the candles only for the sides that have fills', () => {
    const { primitive } = attach();
    expect(primitive.autoscaleInfo()).toBeNull();
    primitive.setMarkers([BUY]);
    const info = primitive.autoscaleInfo();
    expect(info?.priceRange).toBeNull();
    expect(info?.margins?.above).toBe(0);
    expect(info?.margins?.below).toBeGreaterThan(markerHeight(8, 1));
  });

  it('tells the pane where its arrows and prices are, so the close countdown keeps clear of them', () => {
    const { primitive, chart } = attach();
    primitive.setMarkers([SELL]);
    primitive.updateAllViews();
    paint(primitive);
    const [sell] = primitive.px;
    const [arrow, price] = paneWords(chart).rects;
    expect(arrow).toEqual({ left: 108 - sell.size / 2, top: sell.y - sell.size / 2, right: 108 + sell.size / 2,
      bottom: sell.y + sell.size / 2 });
    // '$3.10' is five characters at six pixels, centred on its candle, 12px tall.
    expect(price).toEqual({ left: 108 - 15, top: sell.textY - 6, right: 108 + 15, bottom: sell.textY + 6 });

    primitive.setMarkers([]);
    primitive.updateAllViews();
    paint(primitive);
    expect(paneWords(chart).rects).toEqual([]);

    primitive.setMarkers([SELL]);
    primitive.updateAllViews();
    paint(primitive);
    expect(paneWords(chart).rects).toHaveLength(2);
    primitive.detached();
    expect(paneWords(chart).rects).toEqual([]);
  });
});
