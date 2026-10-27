/**
 * Claude's seat in words and lines (ADR 068): the chart lines from its working orders and armed breaks, when the
 * pill shows, which events toast, and the panel's rows.
 */
import { describe, expect, it } from 'vitest';
import { readClaudeSeat } from './claudeSeatApi';
import { pinned, spread } from './ClaudeSeatChartLayer';
import { SEAT_NOW, seatStatus } from './claudeSeatFixtures';
import {
  buySetRow, claudeChartLines, freshToasts, lineRow, pillShown, seatTone, todayRow,
} from './claudeSeatWords';

describe('claudeChartLines', () => {
  it("draws an armed break as its buy, its stop and its two halves, in the design's words", () => {
    const lines = claudeChartLines(seatStatus(), 'smpl');
    expect(lines.map(l => [l.kind, l.price, l.label])).toEqual([
      ['buy', 4.39, 'Claude · buy 510 on a print at 4.39 (up to 4.41)'],
      ['stop', 4.12, 'Claude · stop 510 at 4.12'],
      ['sell', 4.49, 'Claude · sell 250 at 4.49'],
      ['sell', 4.93, 'Claude · sell 260 at 4.93'],
    ]);
  });

  it('draws working orders after the fill: the stop at its stop price, the targets at their limits', () => {
    const status = seatStatus({
      breaks: [],
      working: [
        { order_id: 7, symbol: 'SMPL', side: 'SELL', order_type: 'STP', qty: 510, limit_price: null, stop_price: 4.12,
          leg_role: 'stop', status: 'Submitted', parent_id: 5 },
        { order_id: 6, symbol: 'SMPL', side: 'SELL', order_type: 'LMT', qty: 250, limit_price: 4.49, stop_price: null,
          leg_role: 'target', status: 'Submitted', parent_id: 5 },
        { order_id: 9, symbol: 'GAPX', side: 'SELL', order_type: 'LMT', qty: 10, limit_price: 2, stop_price: null,
          leg_role: null, status: 'Submitted', parent_id: null },
      ],
    });
    expect(claudeChartLines(status, 'SMPL').map(l => l.label)).toEqual([
      'Claude · stop 510 at 4.12', 'Claude · sell 250 at 4.49',
    ]);
    expect(claudeChartLines(status, 'RUNR')).toEqual([]);
    expect(claudeChartLines(null, 'SMPL')).toEqual([]);
  });
});

describe('the pill and the panel', () => {
  it('shows while the seat is on, "Off" only on a day it was on, nothing otherwise', () => {
    expect(pillShown(seatStatus(), SEAT_NOW)).toBe(true);
    expect(pillShown(seatStatus({ state: 'off', on: false }), SEAT_NOW)).toBe(true);
    expect(pillShown(seatStatus({ state: 'off', on: false }), SEAT_NOW + 86_400)).toBe(false);
    expect(pillShown(seatStatus({ state: 'off', on: false, events: [] }), SEAT_NOW)).toBe(false);
    expect(pillShown(null, SEAT_NOW)).toBe(false);
  });

  it('tones the states as the design draws them', () => {
    expect(seatTone('waiting_line')).toBe('wait');
    expect(seatTone('yielded')).toBe('paused');
    expect(seatTone('done')).toBe('done');
    expect(seatTone('in_trade')).toBe('on');
    expect(seatTone('off')).toBe('off');
  });

  it("writes the panel's rows: the line, the buy set with its risk, and the day with the -$500 stop", () => {
    const status = seatStatus();
    expect(lineRow(status)).toBe('Level 2 + Time & Sales on SMPL · 1 of 3 · you have 2');
    expect(buySetRow(status)).toMatch(/^510 over 4.39 · risk \$148 · ends \d\d:\d\d$/);
    expect(todayRow(status)).toBe('Trades 0 of 3 · $0.00 · I stop for the day at -$500');
    expect(lineRow(seatStatus({ yielded: true }))).toMatch(/you took/);
  });

  it('toasts only the moves that matter, newer than the last read, oldest first', () => {
    const events = [
      { at: 30, kind: 'fill', text: 'bought 510 SMPL at 4.40' },
      { at: 20, kind: 'watch', text: 'watching SMPL' },
      { at: 10, kind: 'break_set', text: 'set buy 510 SMPL' },
    ];
    expect(freshToasts(events, 5).map(e => e.kind)).toEqual(['break_set', 'fill']);
    expect(freshToasts(events, 10).map(e => e.kind)).toEqual(['fill']);
  });

  it('reads the wire and refuses a shape it does not know', () => {
    const read = readClaudeSeat(JSON.parse(JSON.stringify(seatStatus())));
    expect(read?.breaks[0].target2).toBe(4.93);
    expect(read?.reflexes[0].text).toMatch(/4.30 bid/);
    expect(readClaudeSeat({ state: 'dancing' })).toBeNull();
  });
});

describe('chart words off the scale', () => {
  it('pins a price above the pane to its top with an arrow, and below to its bottom', () => {
    expect(pinned(-40, 300)).toEqual({ top: 15, arrow: '↑ ' });
    expect(pinned(120, 300)).toEqual({ top: 120, arrow: '' });
    expect(pinned(340, 300)).toEqual({ top: 296, arrow: '↓ ' });
  });

  it('keeps two words from sitting on each other', () => {
    expect(spread([{ top: 15 }, { top: 15 }, { top: 60 }]).map(w => w.top)).toEqual([15, 30, 60]);
  });
});
