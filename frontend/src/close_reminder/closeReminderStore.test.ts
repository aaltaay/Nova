/** @vitest-environment jsdom */
import { afterEach, describe, expect, it } from 'vitest';
import {
  dueCloseReminders,
  etClock,
  fireKey,
  getCloseReminders,
  noteCloseReminders,
  dismissCloseReminder,
  resetCloseRemindersForTests,
  stageAt,
  type CloseReminder,
} from './closeReminderStore';

// 2026-10-02 is a Friday; EDT is UTC-4 (so 15:50 ET = 19:50Z). 2026-11-05 is a Thursday in EST (UTC-5).
const edt = (day: number, hh: number, mm: number, ss = 0) => new Date(Date.UTC(2026, 9, day, hh + 4, mm, ss));
const est = (day: number, hh: number, mm: number) => new Date(Date.UTC(2026, 10, day, hh + 5, mm));

const held = [{ symbol: 'GRML', qty: 500 }];
const none = new Set<string>();

describe('etClock', () => {
  it('reads New York wall time across the DST change', () => {
    expect(etClock(edt(2, 15, 50))).toEqual({ date: '2026-10-02', minutes: 15 * 60 + 50, weekday: 5 });
    expect(etClock(est(5, 15, 50))).toEqual({ date: '2026-11-05', minutes: 15 * 60 + 50, weekday: 4 });
    expect(etClock(edt(3, 10, 0)).weekday).toBe(6); // Saturday
  });
});

describe('stageAt', () => {
  it('is warn from 15:50, final from 15:55, nothing at 16:00 or before 15:50', () => {
    expect(stageAt(15 * 60 + 49)).toBeNull();
    expect(stageAt(15 * 60 + 50)).toBe('warn');
    expect(stageAt(15 * 60 + 54)).toBe('warn');
    expect(stageAt(15 * 60 + 55)).toBe('final');
    expect(stageAt(16 * 60)).toBeNull();
  });
});

describe('dueCloseReminders', () => {
  it('raises nothing before 15:50, on Sim, on an unknown venue, or at the weekend', () => {
    expect(dueCloseReminders({ positions: held, venue: 'paper', stale: false, now: edt(2, 15, 49), fired: none, current: [] }).reminders).toEqual([]);
    expect(dueCloseReminders({ positions: held, venue: 'sim', stale: false, now: edt(2, 15, 52), fired: none, current: [] }).reminders).toEqual([]);
    expect(dueCloseReminders({ positions: held, venue: null, stale: false, now: edt(2, 15, 52), fired: none, current: [] }).reminders).toEqual([]);
    expect(dueCloseReminders({ positions: held, venue: 'paper', stale: false, now: edt(3, 15, 52), fired: none, current: [] }).reminders).toEqual([]);
  });

  it('raises one warn card per open position at 15:50 and skips flat rows', () => {
    const res = dueCloseReminders({
      positions: [...held, { symbol: 'APUS', qty: 0 }, { symbol: 'nxl', qty: -200 }],
      venue: 'paper', stale: false, now: edt(2, 15, 50), fired: none, current: [],
    });
    expect(res.reminders.map(r => [r.symbol, r.qty, r.stage])).toEqual([['GRML', 500, 'warn'], ['NXL', -200, 'warn']]);
    expect(res.newKeys).toEqual([fireKey('2026-10-02', 'paper', 'GRML', 'warn'), fireKey('2026-10-02', 'paper', 'NXL', 'warn')]);
  });

  it('does not raise a dismissed card again at the same stage, and escalates it at 15:55', () => {
    const warnKey = fireKey('2026-10-02', 'paper', 'GRML', 'warn');
    const again = dueCloseReminders({ positions: held, venue: 'paper', stale: false, now: edt(2, 15, 53), fired: new Set([warnKey]), current: [] });
    expect(again.reminders).toEqual([]);
    expect(again.newKeys).toEqual([]);
    const final = dueCloseReminders({ positions: held, venue: 'paper', stale: false, now: edt(2, 15, 55), fired: new Set([warnKey]), current: [] });
    expect(final.reminders.map(r => r.stage)).toEqual(['final']);
    expect(final.newKeys).toEqual([fireKey('2026-10-02', 'paper', 'GRML', 'final')]);
  });

  it('keeps an unchanged card as the same object and retires a position that went flat', () => {
    const card: CloseReminder = { symbol: 'GRML', qty: 500, venue: 'paper', stage: 'warn', stale: false, at: 1 };
    const warnKey = fireKey('2026-10-02', 'paper', 'GRML', 'warn');
    const same = dueCloseReminders({ positions: held, venue: 'paper', stale: false, now: edt(2, 15, 52), fired: new Set([warnKey]), current: [card] });
    expect(same.reminders[0]).toBe(card);
    const flat = dueCloseReminders({ positions: [{ symbol: 'GRML', qty: 0 }], venue: 'paper', stale: false, now: edt(2, 15, 52), fired: new Set([warnKey]), current: [card] });
    expect(flat.reminders).toEqual([]);
  });

  it('clears every card at 16:00', () => {
    const card: CloseReminder = { symbol: 'GRML', qty: 500, venue: 'paper', stage: 'final', stale: false, at: 1 };
    expect(dueCloseReminders({ positions: held, venue: 'paper', stale: false, now: edt(2, 16, 0), fired: none, current: [card] }).reminders).toEqual([]);
  });
});

describe('the store', () => {
  afterEach(() => resetCloseRemindersForTests());

  it('raises, remembers a dismissal for the day across a reload, and escalates', () => {
    noteCloseReminders(held, 'paper', false, edt(2, 15, 50, 5));
    expect(getCloseReminders().map(r => r.stage)).toEqual(['warn']);
    dismissCloseReminder('GRML');
    expect(getCloseReminders()).toEqual([]);
    noteCloseReminders(held, 'paper', false, edt(2, 15, 51));
    expect(getCloseReminders()).toEqual([]); // the warn key is fired for the day
    const stored = JSON.parse(localStorage.getItem('nova.closeReminder.fired') ?? 'null'); // prefStore's envelope
    expect(stored.value).toMatchObject({ schema_version: 1, date: '2026-10-02', keys: [fireKey('2026-10-02', 'paper', 'GRML', 'warn')] });
    noteCloseReminders(held, 'paper', true, edt(2, 15, 55));
    expect(getCloseReminders().map(r => [r.stage, r.stale])).toEqual([['final', true]]);
    noteCloseReminders(held, 'paper', false, edt(2, 16, 0));
    expect(getCloseReminders()).toEqual([]);
  });
});
