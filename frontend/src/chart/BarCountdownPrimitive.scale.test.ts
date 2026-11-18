import type { SeriesAttachedParameter, SeriesType, Time } from 'lightweight-charts';
import { describe, expect, it, vi } from 'vitest';
import { BarCountdownPrimitive } from './BarCountdownPrimitive';
import { CHART_BAR_COUNTDOWN_SCALE_BACK_COLOR, CHART_BAR_COUNTDOWN_SCALE_TEXT_COLOR } from './barCountdownConstants';

const chartSec = (iso: string) => Date.parse(`${iso}Z`) / 1000;
const edt = (etIso: string) => Date.parse(`${etIso}-04:00`);
const TIP = { time: chartSec('2026-09-24T09:31:00'), open: 4.8, high: 5.5, low: 4.75, close: 5 };
const UP = '#26a69a';
const DOWN = '#ef5350';

function attach(onScale: boolean, lastBar: Record<string, unknown> | null = TIP, options: unknown = { upColor: UP, downColor: DOWN }) {
  const requestUpdate = vi.fn();
  const series = {
    dataByIndex: () => lastBar, priceToCoordinate: (price: number) => 1000 - price * 100, options: () => options,
  };
  const chart = {
    timeScale: () => ({ timeToCoordinate: () => 200, options: () => ({ barSpacing: 8 }) }),
    options: () => ({ layout: { fontSize: 10 } }),
  };
  const primitive = new BarCountdownPrimitive('1Min', onScale);
  primitive.attached({ chart, series, requestUpdate } as unknown as SeriesAttachedParameter<Time, SeriesType>);
  return { primitive, requestUpdate };
}

describe('the candle countdown on the price scale (the phone\'s charts)', () => {
  it('is a chip by the candle on the desk, and nothing on the scale', () => {
    const { primitive } = attach(false);
    expect(primitive.paneViews()).toHaveLength(1);
    expect(primitive.priceAxisViews()).toHaveLength(0);
  });

  it('on the scale it draws no chip over the candles, and one label touching the last price from below', () => {
    const { primitive } = attach(true);
    primitive.setNow(edt('2026-09-24T09:31:18'));
    expect(primitive.paneViews()).toHaveLength(0);
    const [label] = primitive.priceAxisViews();
    expect(label.visible?.()).toBe(true);
    expect(label.text()).toBe('00:42');
    // The last price (5.00) is drawn at y 500; the countdown is exactly one scale label (10 px type: 10 x 17/12)
    // under it, so the two touch.
    expect(label.coordinate()).toBeCloseTo(500 + (10 * 17) / 12, 6);
    expect(label.tickVisible?.()).toBe(false);
  });

  it("takes the last price label's colours: the candle's own, and white (mockup A, 2026-11-17)", () => {
    const up = attach(true);
    up.primitive.setNow(edt('2026-09-24T09:31:18'));
    expect(up.primitive.priceAxisViews()[0].backColor()).toBe(UP);          // closed over its open
    expect(up.primitive.priceAxisViews()[0].textColor()).toBe(CHART_BAR_COUNTDOWN_SCALE_TEXT_COLOR);
    const down = attach(true, { ...TIP, open: 5.2 });
    down.primitive.setNow(edt('2026-09-24T09:31:18'));
    expect(down.primitive.priceAxisViews()[0].backColor()).toBe(DOWN);
    const flat = attach(true, { ...TIP, open: 5 });
    expect(flat.primitive.priceAxisViews()[0].backColor()).toBe(UP);        // a flat candle is drawn up, as the chart does
    const own = attach(true, { ...TIP, color: '#123456' });
    expect(own.primitive.priceAxisViews()[0].backColor()).toBe('#123456');  // a candle with its own colour
    const unread = attach(true, TIP, {});
    expect(unread.primitive.priceAxisViews()[0].backColor()).toBe(CHART_BAR_COUNTDOWN_SCALE_BACK_COLOR);
  });

  it('stays white in the last seconds (amber cannot be read on the candle colour), and repaints only when the digits change', () => {
    const { primitive, requestUpdate } = attach(true);
    primitive.setNow(edt('2026-09-24T09:31:55'));
    const [label] = primitive.priceAxisViews();
    expect(label.text()).toBe('00:05');
    expect(label.textColor()).toBe(CHART_BAR_COUNTDOWN_SCALE_TEXT_COLOR);
    const painted = requestUpdate.mock.calls.length;
    primitive.setNow(edt('2026-09-24T09:31:55.600'));
    expect(requestUpdate.mock.calls.length).toBe(painted);
  });

  it('shows no label without a clock or a candle', () => {
    const { primitive } = attach(true);
    expect(primitive.priceAxisViews()[0].visible?.()).toBe(false);
    const empty = attach(true, null);
    empty.primitive.setNow(edt('2026-09-24T09:31:18'));
    expect(empty.primitive.priceAxisViews()[0].visible?.()).toBe(false);
  });
});
