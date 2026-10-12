/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { gateToast, type GateContext } from './toastGate';
import {
  etMinutesOf,
  getToastWindow,
  inToastWindow,
  resetToastWindow,
  resetToastWindowForTests,
  saveToastWindow,
  toastWindowOpen,
  tradingDayOf,
} from './toastWindow';
import { WATCH_TOAST_WINDOW_KEY } from './watchListConstants';

describe("the toasts' Eastern clock", () => {
  it('reads the minute of the day and the trading day, which starts at 04:00 ET', () => {
    expect(etMinutesOf(Date.UTC(2026, 8, 23, 14, 14, 5))).toBe(10 * 60 + 14);    // EDT: UTC-4
    expect(etMinutesOf(Date.UTC(2026, 11, 1, 14, 0))).toBe(9 * 60);              // EST: UTC-5
    expect(tradingDayOf(Date.UTC(2026, 8, 23, 7, 59))).toBe('2026-09-22');       // 03:59 ET
    expect(tradingDayOf(Date.UTC(2026, 8, 23, 8, 0))).toBe('2026-09-23');        // 04:00 ET
  });
});

describe('the toast window', () => {
  beforeEach(() => {
    localStorage.clear();
    resetToastWindowForTests();
  });
  afterEach(() => {
    localStorage.clear();
    resetToastWindowForTests();
  });

  it('is 07:00-16:00 ET by default, start inclusive, end exclusive', () => {
    expect(getToastWindow()).toEqual({ start: '07:00', end: '16:00' });
    expect(inToastWindow(getToastWindow(), 7 * 60)).toBe(true);
    expect(inToastWindow(getToastWindow(), 16 * 60)).toBe(false);
    expect(toastWindowOpen(Date.UTC(2026, 8, 23, 10, 59))).toBe(false);           // 06:59 ET
  });

  it('saves a window, refuses one that ends before it starts, and resets to the default', () => {
    expect(saveToastWindow({ start: '07:00', end: '10:00' })).toBeNull();
    resetToastWindowForTests();
    expect(getToastWindow()).toEqual({ start: '07:00', end: '10:00' });           // read back from storage
    expect(saveToastWindow({ start: '10:00', end: '09:30' })).toBe('The end must be after the start');
    expect(saveToastWindow({ start: '7am', end: '10:00' })).toBe('A time is HH:MM, Eastern');
    expect(getToastWindow()).toEqual({ start: '07:00', end: '10:00' });
    resetToastWindow();
    expect(getToastWindow()).toEqual({ start: '07:00', end: '16:00' });
  });

  it('reads an unknown version as the default and says so', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    localStorage.setItem(WATCH_TOAST_WINDOW_KEY, JSON.stringify({ schema_version: 2, start: '09:00', end: '10:00' }));
    expect(getToastWindow()).toEqual({ start: '07:00', end: '16:00' });
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });
});

describe('gateToast', () => {
  const ctx = (patch: Partial<GateContext> = {}): GateContext => ({
    nowMs: 1_000, day: '2026-09-23', inWindow: true, how: 'star', onScreen: false, ...patch,
  });

  it("forgets a day's quiet periods and joins at the next trading day", () => {
    const first = gateToast(null, { kind: 'hod', symbol: 'GRML', runningUp: false }, ctx());
    expect(first.verdict).toEqual({ verdict: 'raise' });
    const quiet = gateToast(first.memory, { kind: 'hod', symbol: 'GRML', runningUp: false }, ctx({ nowMs: 2_000 }));
    expect(quiet.verdict).toEqual({ verdict: 'hold', reason: 'quiet' });
    const nextDay = gateToast(quiet.memory, { kind: 'hod', symbol: 'GRML', runningUp: false },
      ctx({ nowMs: 3_000, day: '2026-09-24' }));
    expect(nextDay.verdict).toEqual({ verdict: 'raise' });
  });

  it('holds a join outside the window once, and never announces it later that day', () => {
    const held = gateToast(null, { kind: 'join', symbol: 'GIXI' }, ctx({ how: 'auto', inWindow: false }));
    expect(held.verdict).toEqual({ verdict: 'hold', reason: 'outside_window' });
    expect(gateToast(held.memory, { kind: 'join', symbol: 'GIXI' }, ctx({ how: 'auto' })).verdict)
      .toEqual({ verdict: 'ignore' });
    expect(gateToast(null, { kind: 'join', symbol: 'MINE' }, ctx()).verdict).toEqual({ verdict: 'ignore' });
    expect(gateToast(null, { kind: 'hod', symbol: 'NOPE', runningUp: false }, ctx({ how: null })).verdict)
      .toEqual({ verdict: 'ignore' });
  });
});
