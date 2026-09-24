import type { SeriesAttachedParameter, SeriesType, Time } from 'lightweight-charts';
import { describe, expect, it, vi } from 'vitest';
import { BarCountdownPrimitive, type BarCountdownPaneView } from './BarCountdownPrimitive';
import {
  CHART_BAR_COUNTDOWN_TEXT_COLOR,
  CHART_BAR_COUNTDOWN_WARN_COLOR,
} from './barCountdownConstants';

const chartSec = (iso: string) => Date.parse(`${iso}Z`) / 1000;
const edt = (etIso: string) => Date.parse(`${etIso}-04:00`);

function attach(lastBar: { time: number; high: number; low: number; close: number } | null) {
  const requestUpdate = vi.fn();
  const dataByIndex = vi.fn(() => lastBar);
  const series = {
    dataByIndex,
    priceToCoordinate: (price: number) => 1000 - price * 100,
  };
  const chart = {
    timeScale: () => ({
      timeToCoordinate: (time: Time) => (time === lastBar?.time ? 200 : null),
      options: () => ({ barSpacing: 8 }),
    }),
  };
  const primitive = new BarCountdownPrimitive('1Min');
  primitive.attached({ chart, series, requestUpdate } as unknown as SeriesAttachedParameter<Time, SeriesType>);
  const view = primitive.paneViews()[0] as BarCountdownPaneView;
  return { primitive, view, requestUpdate, dataByIndex };
}

const TIP = { time: chartSec('2026-09-24T09:31:00'), high: 5.5, low: 4.75, close: 5 };

describe('BarCountdownPrimitive', () => {
  it('reads the newest bar by search, not by copying the series', () => {
    const { primitive, dataByIndex } = attach(TIP);
    primitive.setNow(edt('2026-09-24T09:31:18'));
    expect(dataByIndex).toHaveBeenCalledWith(Number.MAX_SAFE_INTEGER, -1);
  });

  it('repaints only when the digits change', () => {
    const { primitive, requestUpdate } = attach(TIP);
    requestUpdate.mockClear();
    primitive.setNow(edt('2026-09-24T09:31:18.100'));
    primitive.setNow(edt('2026-09-24T09:31:18.900'));
    expect(requestUpdate).toHaveBeenCalledTimes(1);
    primitive.setNow(edt('2026-09-24T09:31:19'));
    expect(requestUpdate).toHaveBeenCalledTimes(2);
    primitive.setNow(null);
    expect(requestUpdate).toHaveBeenCalledTimes(3);
    primitive.setNow(null);
    expect(requestUpdate).toHaveBeenCalledTimes(3);
  });

  it('anchors over the forming candle wick', () => {
    const { primitive, view } = attach(TIP);
    primitive.setNow(edt('2026-09-24T09:31:18'));
    primitive.updateAllViews();
    expect(view.data).toEqual({ anchorX: 200, wickTopY: 450, wickBottomY: 525, text: '00:42', warn: false });
  });

  it('anchors in the next slot at the last price before this period prints', () => {
    const { primitive, view } = attach(TIP);
    primitive.setNow(edt('2026-09-24T09:32:05'));
    primitive.updateAllViews();
    expect(view.data).toEqual({ anchorX: 208, wickTopY: 500, wickBottomY: 500, text: '00:55', warn: false });
  });

  it('draws nothing without a clock, a bar, or once detached', () => {
    const idle = attach(TIP);
    idle.primitive.updateAllViews();
    expect(idle.view.data).toBeNull();

    const empty = attach(null);
    empty.primitive.setNow(edt('2026-09-24T09:31:18'));
    empty.primitive.updateAllViews();
    expect(empty.view.data).toBeNull();

    const gone = attach(TIP);
    gone.primitive.setNow(edt('2026-09-24T09:31:18'));
    gone.primitive.detached();
    gone.primitive.updateAllViews();
    expect(gone.view.data).toBeNull();
  });

  it('paints the digits in the chip, warning colour at the end', () => {
    const { primitive, view } = attach(TIP);
    const paint = (at: string) => {
      primitive.setNow(edt(at));
      primitive.updateAllViews();
      const ctx = {
        save: vi.fn(), restore: vi.fn(), beginPath: vi.fn(), roundRect: vi.fn(), rect: vi.fn(),
        fill: vi.fn(), stroke: vi.fn(), fillText: vi.fn(),
        measureText: (text: string) => ({ width: text.length * 6 }),
        font: '', fillStyle: '', strokeStyle: '', lineWidth: 0, textAlign: '', textBaseline: '',
      };
      const target = {
        useMediaCoordinateSpace: (draw: (scope: unknown) => void) =>
          draw({ context: ctx, mediaSize: { width: 600, height: 300 } }),
      };
      view.renderer().draw(target as never);
      return ctx;
    };
    const calm = paint('2026-09-24T09:31:18');
    expect(calm.fillText).toHaveBeenCalledWith('00:42', expect.any(Number), expect.any(Number));
    expect(calm.fillStyle).toBe(CHART_BAR_COUNTDOWN_TEXT_COLOR);
    expect(calm.roundRect).toHaveBeenCalledTimes(1);
    const late = paint('2026-09-24T09:31:55');
    expect(late.fillText).toHaveBeenCalledWith('00:05', expect.any(Number), expect.any(Number));
    expect(late.fillStyle).toBe(CHART_BAR_COUNTDOWN_WARN_COLOR);
  });
});
