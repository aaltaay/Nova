import type { SeriesAttachedParameter, SeriesType, Time } from 'lightweight-charts';
import { describe, expect, it, vi } from 'vitest';
import { SessionHighlightingPrimitive } from './SessionHighlightingPrimitive';
import { sessionColorForChartTime } from './sessionHighlight';

// Chart times are ET wall clock as UTC seconds: 09:29 and 09:30 sit either side of the open.
const at = (hhmm: string) => Date.parse(`2026-10-02T${hhmm}:00Z`) / 1000;

function attach(initial: number[]) {
  const bars = initial.map(time => ({ time }));
  let onData: ((scope: 'full' | 'update') => void) | null = null;
  const requestUpdate = vi.fn();
  const series = {
    data: vi.fn(() => bars.map(b => ({ ...b }))),
    dataByIndex: vi.fn(() => bars[bars.length - 1] ?? null),
    subscribeDataChanged: (fn: (scope: 'full' | 'update') => void) => { onData = fn; },
    unsubscribeDataChanged: vi.fn(),
  };
  const primitive = new SessionHighlightingPrimitive();
  primitive.attached({ chart: {}, series, requestUpdate } as unknown as SeriesAttachedParameter<Time, SeriesType>);
  requestUpdate.mockClear();
  series.data.mockClear();
  const tick = (scope: 'full' | 'update') => onData?.(scope);
  return { primitive, requestUpdate, series, bars, tick };
}

describe('SessionHighlightingPrimitive', () => {
  it('a tick on the forming bar changes nothing and asks for no redraw', () => {
    const { primitive, requestUpdate, series, tick } = attach([at('09:28'), at('09:29')]);
    const before = primitive.backgroundColors;
    tick('update');
    expect(primitive.backgroundColors).toBe(before);
    expect(series.data).not.toHaveBeenCalled();
    expect(requestUpdate).not.toHaveBeenCalled();
  });

  it('a new bar is coloured on its own, without copying the series or a full redraw', () => {
    const { primitive, requestUpdate, series, bars, tick } = attach([at('09:28'), at('09:29')]);
    bars.push({ time: at('09:30') });
    tick('update');
    expect(primitive.backgroundColors.map(c => c.time)).toEqual([at('09:28'), at('09:29'), at('09:30')]);
    expect(primitive.backgroundColors[2].color).toBe(sessionColorForChartTime(at('09:30') as Time));
    expect(primitive.backgroundColors[2].color).not.toBe(primitive.backgroundColors[1].color);
    expect(series.data).not.toHaveBeenCalled();
    expect(requestUpdate).not.toHaveBeenCalled();
  });

  it('new data from the store rebuilds every colour', () => {
    const { primitive, series, bars, tick } = attach([at('09:28')]);
    bars.splice(0, 1, { time: at('09:00') }, { time: at('09:01') });
    tick('full');
    expect(series.data).toHaveBeenCalledTimes(1);
    expect(primitive.backgroundColors.map(c => c.time)).toEqual([at('09:00'), at('09:01')]);
  });

  it('refresh redraws only when the bars changed', () => {
    const { primitive, requestUpdate, bars } = attach([at('09:28')]);
    primitive.refresh();
    expect(requestUpdate).not.toHaveBeenCalled();
    bars.push({ time: at('09:29') });
    primitive.refresh();
    expect(requestUpdate).toHaveBeenCalledTimes(1);
  });
});
