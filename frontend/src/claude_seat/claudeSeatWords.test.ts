/**
 * Claude's seat in words and lines (ADR 068): the chart lines from its working orders and armed breaks, when the
 * pill shows, which events toast, and the panel's rows.
 */
import { describe, expect, it } from 'vitest';
import { readClaudeSeat } from './claudeSeatApi';
import { pinned, spread } from './ClaudeSeatChartLayer';
import { seatStatus } from './claudeSeatFixtures';
import {
  buySetRow, claudeChartLines, eventWords, freshToasts, lineRow, pillShown, pillTone, seatTone, switchTip, todayRow,
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
  it('shows whenever the seat was read: on, and "Off" every day, even one it was never on', () => {
    expect(pillShown(seatStatus())).toBe(true);
    expect(pillShown(seatStatus({ state: 'off', on: false }))).toBe(true);
    expect(pillShown(seatStatus({ state: 'off', on: false, events: [] }))).toBe(true);
    expect(pillShown(null)).toBe(false);
  });

  it('tones the states as the design draws them', () => {
    expect(seatTone('waiting_line')).toBe('wait');
    expect(seatTone('done')).toBe('done');
    expect(seatTone('in_trade')).toBe('on');
    expect(seatTone('off')).toBe('off');
  });

  it('mutes the pill while the switch is Off, whatever Claude watches, and keeps a done day red (ADR 072)', () => {
    const off = { on: false, at: null, can_turn_on: true, why_not_on: null };
    expect(pillTone(seatStatus())).toBe('on');
    expect(pillTone(seatStatus({ switch: off }))).toBe('off');
    expect(pillTone(seatStatus({ switch: off, state: 'done' }))).toBe('done');
    expect(pillTone(seatStatus({ switch: null }))).toBe('on');
  });

  it("tips the switch with what a press does, or the refusal On would meet, in Nova's words", () => {
    const refused = { on: false, at: null, can_turn_on: false,
      why_not_on: { reason: 'TRADER_PAST_FLAT_BY', error: 'Claude stays Off after 15:55 ET.' } };
    expect(switchTip(refused, false)).toBe('Claude stays Off after 15:55 ET.');
    expect(switchTip({ ...refused, can_turn_on: true, why_not_on: null }, false)).toMatch(/^Claude's switch: Off\./);
    expect(switchTip({ on: true, at: null, can_turn_on: true, why_not_on: null }, false)).toMatch(/yours to close/);
    expect(switchTip(refused, true)).toMatch(/Waiting for Nova/);
  });

  it("writes the panel's rows: the line, the buy set with its risk, and the day with the -$500 stop", () => {
    const status = seatStatus();
    expect(lineRow(status)).toBe("Level 2 + Time & Sales on SMPL · Claude's lane");
    expect(buySetRow(status)).toMatch(/^510 over 4.39 · risk \$148 · ends \d\d:\d\d$/);
    expect(todayRow(status)).toBe('Trades 0 · no cap · $0.00 · I stop for the day at -$500');
    expect(todayRow(seatStatus({ today: { ...status.today, entries: 2, max_entries: 3 } })))
      .toBe('Trades 2 of 3 · $0.00 · I stop for the day at -$500');
    expect(lineRow(seatStatus({ state: 'idle', line: { symbol: null, depth: false, tape: false, why_not: null } })))
      .toBe('None yet');
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

  it("toasts the switch turned Off and each trade it handed you, in the backend's own sentences (ADR 072)", () => {
    const events = [
      { at: 41, kind: 'handed', text: 'Claude is off: its 300 SMPL are yours to close. Its stop at 4 keeps resting.' },
      { at: 40, kind: 'switch_off', text: 'Claude is off: no new trades.' },
      { at: 39, kind: 'yielded', text: 'gave you its line' },
    ];
    const toasts = freshToasts(events, 5);
    expect(toasts.map(e => e.kind)).toEqual(['switch_off', 'handed']);
    expect(toasts.map(eventWords)).toEqual([
      'Claude is off: no new trades.',
      'Claude is off: its 300 SMPL are yours to close. Its stop at 4 keeps resting.',
    ]);
    expect(eventWords({ at: 1, kind: 'fill', text: 'bought 510 SMPL at 4.40' })).toBe('Claude bought 510 SMPL at 4.40');
  });

  it('reads the wire and refuses a shape it does not know', () => {
    const read = readClaudeSeat(JSON.parse(JSON.stringify(seatStatus())));
    expect(read?.breaks[0].target2).toBe(4.93);
    expect(read?.reflexes[0].text).toMatch(/4.30 bid/);
    expect(readClaudeSeat({ state: 'dancing' })).toBeNull();
    // The retired state is a shape this desk no longer reads (ADR 072).
    expect(readClaudeSeat({ ...seatStatus(), state: 'yielded' })).toBeNull();
  });

  it("reads the switch, and its refusal's words (ADR 072)", () => {
    const read = readClaudeSeat({ ...seatStatus(), switch: {
      on: false, at: 12, can_turn_on: false, why_not_on: { reason: 'TRADER_DAY_STOP', error: 'Claude reached its day stop.' },
    } });
    expect(read?.switch).toEqual({
      on: false, at: 12, can_turn_on: false, why_not_on: { reason: 'TRADER_DAY_STOP', error: 'Claude reached its day stop.' },
    });
    const older: Record<string, unknown> = { ...seatStatus() };
    delete older.switch;
    expect(readClaudeSeat(older)?.switch).toBeNull();
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
