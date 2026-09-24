import type { Time } from 'lightweight-charts';
import { describe, expect, it } from 'vitest';
import {
  barCountdown,
  barCountdownChipBox,
  barCountdownPeriodSec,
  formatBarCountdown,
  type BarCountdownBar,
} from './barCountdown';

/** An Eastern wall time as the chart encodes it (UTC seconds). */
const chartSec = (iso: string) => Date.parse(`${iso}Z`) / 1000;
const bar = (etIso: string): BarCountdownBar => ({
  time: chartSec(etIso) as Time, high: 5.4, low: 4.8, close: 5.0,
});
/** Thursday 2026-09-24 is on EDT (UTC-4). */
const edt = (etIso: string) => Date.parse(`${etIso}-04:00`);

describe('barCountdownPeriodSec', () => {
  it('counts down minute candles only', () => {
    expect(barCountdownPeriodSec('1Min')).toBe(60);
    expect(barCountdownPeriodSec('5Min')).toBe(300);
    expect(barCountdownPeriodSec('15Min')).toBe(900);
    for (const tf of ['10Sec', '1Hour', '4Hour', '1Day', '1Week', '0Min', 'Min', '']) {
      expect(barCountdownPeriodSec(tf)).toBeNull();
    }
  });
});

describe('formatBarCountdown', () => {
  it('reads mm:ss, with hours past an hour', () => {
    expect(formatBarCountdown(42)).toBe('00:42');
    expect(formatBarCountdown(222)).toBe('03:42');
    expect(formatBarCountdown(3723)).toBe('1:02:03');
    expect(formatBarCountdown(-3)).toBe('00:00');
  });
});

describe('barCountdown', () => {
  it('counts the 1-minute candle forming at the tip down to its close', () => {
    expect(barCountdown(edt('2026-09-24T09:31:18'), '1Min', bar('2026-09-24T09:31:00'))).toEqual({
      remainingSec: 42, text: '00:42', warn: false, anchor: 'tip',
    });
  });

  it('counts the 5-minute candle from its own bucket, not the minute', () => {
    const cd = barCountdown(edt('2026-09-24T09:31:18'), '5Min', bar('2026-09-24T09:30:00'));
    expect(cd).toMatchObject({ remainingSec: 222, text: '03:42', anchor: 'tip' });
  });

  it('puts the countdown in the next slot while nothing has printed this period', () => {
    const cd = barCountdown(edt('2026-09-24T09:31:18'), '1Min', bar('2026-09-24T09:29:00'));
    expect(cd).toMatchObject({ remainingSec: 42, anchor: 'next' });
  });

  it('starts the next candle at a full period on the boundary', () => {
    const cd = barCountdown(edt('2026-09-24T09:32:00'), '1Min', bar('2026-09-24T09:31:00'));
    expect(cd).toMatchObject({ remainingSec: 60, text: '01:00', anchor: 'next' });
  });

  it('follows a print that beat the clock across the boundary', () => {
    const cd = barCountdown(edt('2026-09-24T09:31:59.600'), '1Min', bar('2026-09-24T09:32:00'));
    expect(cd).toMatchObject({ remainingSec: 60, anchor: 'tip' });
  });

  it('says nothing when the newest bar is more than a period ahead of the clock', () => {
    expect(barCountdown(edt('2026-09-24T09:31:10'), '1Min', bar('2026-09-24T09:33:00'))).toBeNull();
  });

  it('warns through the last ten seconds', () => {
    const at = (s: string) => barCountdown(edt(`2026-09-24T09:31:${s}`), '1Min', bar('2026-09-24T09:31:00'));
    expect(at('49')?.warn).toBe(false);
    expect(at('50')).toMatchObject({ remainingSec: 10, warn: true });
    expect(at('59')).toMatchObject({ remainingSec: 1, text: '00:01', warn: true });
  });

  it('follows Eastern standard time in winter', () => {
    const now = Date.parse('2026-12-01T10:00:30-05:00');
    expect(barCountdown(now, '1Min', bar('2026-12-01T10:00:00'))?.remainingSec).toBe(30);
  });

  it('runs through the whole 04:00-20:00 session and stops outside it', () => {
    const last = bar('2026-09-24T04:00:00');
    expect(barCountdown(edt('2026-09-24T04:00:20'), '1Min', last)?.remainingSec).toBe(40);
    expect(barCountdown(edt('2026-09-24T03:59:59'), '1Min', last)).toBeNull();
    const late = bar('2026-09-24T19:55:00');
    expect(barCountdown(edt('2026-09-24T19:59:30'), '5Min', late)?.remainingSec).toBe(30);
    expect(barCountdown(edt('2026-09-24T20:00:05'), '5Min', late)).toBeNull();
  });

  it('says nothing on a weekend', () => {
    const sat = Date.parse('2026-09-26T10:00:10-04:00');
    expect(barCountdown(sat, '1Min', bar('2026-09-26T10:00:00'))).toBeNull();
  });

  it("says nothing before today's first print (or on a holiday, which has none)", () => {
    expect(barCountdown(edt('2026-09-24T07:00:10'), '1Min', bar('2026-09-23T19:59:00'))).toBeNull();
  });

  it('needs a clock, a bar, an intraday time and a minute timeframe', () => {
    const last = bar('2026-09-24T09:31:00');
    const now = edt('2026-09-24T09:31:18');
    expect(barCountdown(null, '1Min', last)).toBeNull();
    expect(barCountdown(Number.NaN, '1Min', last)).toBeNull();
    expect(barCountdown(now, '1Min', null)).toBeNull();
    expect(barCountdown(now, '1Min', { ...last, time: '2026-09-24' as Time })).toBeNull();
    expect(barCountdown(now, '10Sec', last)).toBeNull();
    expect(barCountdown(now, '1Day', last)).toBeNull();
  });
});

describe('barCountdownChipBox', () => {
  const base = { anchorX: 100, wickTopY: 50, wickBottomY: 80, textWidth: 30, paneWidth: 600, paneHeight: 300 };

  it('centres the chip over the candle, just above its wick', () => {
    expect(barCountdownChipBox(base)).toEqual({ x: 80, y: 28, width: 40, height: 16 });
  });

  it('drops under the candle when the top of the pane leaves no room', () => {
    expect(barCountdownChipBox({ ...base, wickTopY: 10 })?.y).toBe(86);
  });

  it('stays inside the pane when neither side has room', () => {
    expect(barCountdownChipBox({ ...base, wickTopY: 10, paneHeight: 90 })?.y).toBe(2);
    expect(barCountdownChipBox({ ...base, wickTopY: 900, wickBottomY: 950 })?.y).toBe(282);
  });

  it('keeps the chip whole at the right edge', () => {
    expect(barCountdownChipBox({ ...base, anchorX: 595 })?.x).toBe(558);
    expect(barCountdownChipBox({ ...base, anchorX: 3 })?.x).toBe(2);
  });

  it('hides when the candle is scrolled out of the pane or off the price scale', () => {
    expect(barCountdownChipBox({ ...base, anchorX: -5 })).toBeNull();
    expect(barCountdownChipBox({ ...base, anchorX: 601 })).toBeNull();
    expect(barCountdownChipBox({ ...base, anchorX: null })).toBeNull();
    expect(barCountdownChipBox({ ...base, wickTopY: null })).toBeNull();
  });
});
