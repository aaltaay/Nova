import type { SeriesAttachedParameter, SeriesType, Time } from 'lightweight-charts';
import { describe, expect, it, vi } from 'vitest';
import { BarCountdownPrimitive } from './BarCountdownPrimitive';
import { CHART_BAR_COUNTDOWN_TEXT_COLOR, CHART_BAR_COUNTDOWN_WARN_COLOR } from './barCountdownConstants';

const chartSec = (iso: string) => Date.parse(`${iso}Z`) / 1000;
const edt = (etIso: string) => Date.parse(`${etIso}-04:00`);
const TIP = { time: chartSec('2026-09-24T09:31:00'), high: 5.5, low: 4.75, close: 5 };

function attach(onScale: boolean, lastBar: typeof TIP | null = TIP) {
  const requestUpdate = vi.fn();
  const series = { dataByIndex: () => lastBar, priceToCoordinate: (price: number) => 1000 - price * 100 };
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

  it('on the scale it draws no chip over the candles, and one label under the last price', () => {
    const { primitive } = attach(true);
    primitive.setNow(edt('2026-09-24T09:31:18'));
    expect(primitive.paneViews()).toHaveLength(0);
    const [label] = primitive.priceAxisViews();
    expect(label.visible?.()).toBe(true);
    expect(label.text()).toBe('00:42');
    // The last price (5.00) is drawn at y 500; the countdown sits one label's height under it.
    expect(label.coordinate()).toBe(500 + 10 + 7);
    expect(label.textColor()).toBe(CHART_BAR_COUNTDOWN_TEXT_COLOR);
    expect(label.tickVisible?.()).toBe(false);
  });

  it('turns the warning colour in the last seconds, and repaints only when the digits change', () => {
    const { primitive, requestUpdate } = attach(true);
    primitive.setNow(edt('2026-09-24T09:31:55'));
    const [label] = primitive.priceAxisViews();
    expect(label.text()).toBe('00:05');
    expect(label.textColor()).toBe(CHART_BAR_COUNTDOWN_WARN_COLOR);
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
