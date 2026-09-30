/**
 * Share clips' tab tracker (ADR 039): a window's Trader tab report is read
 * once, a symbol's tab is found shown or hidden with the reason, and the
 * last half hour is kept so "save the last 5 min" knows where the tab was.
 */
import { describe, expect, it } from 'vitest';
import { createTabTracker, readTabReport, stateFor } from '../../electron/clipTabs.mjs';

const report = (over: Record<string, unknown> = {}) => ({
  schema_version: 1,
  window_id: 'main',
  visible: true,
  reason: null,
  symbol: 'PFSA',
  pane: { x: 200, y: 90, w: 1200, h: 700 },
  panels: { plan: { x: 1000, y: 120, w: 300, h: 150 }, bogus: { x: 1, y: 1, w: 1, h: 1 } },
  inner: { w: 2560, h: 1392 },
  ...over,
});

function fakeWindow(id: number, content = { x: 0, y: 23, width: 2560, height: 1392 }) {
  let minimized = false;
  return {
    webContents: { id },
    getContentBounds: () => content,
    isMinimized: () => minimized,
    minimize: () => { minimized = true; },
    restore: () => { minimized = false; },
  };
}
const screen = { getDisplayMatching: () => ({ id: 1449598500 }) };

describe('readTabReport', () => {
  it('keeps what it knows and drops what it does not', () => {
    const r = readTabReport(report());
    expect(r).toMatchObject({ windowId: 'main', visible: true, symbol: 'PFSA', pane: { x: 200, y: 90, w: 1200, h: 700 } });
    expect(Object.keys(r!.panels)).toEqual(['plan']);
    expect(readTabReport(report({ schema_version: 2 }))).toBeNull();
    expect(readTabReport(report({ inner: { w: 0, h: 0 } }))).toBeNull();
    expect(readTabReport(report({ symbol: 'nope nope' }))?.symbol).toBeNull();
  });
});

describe('stateFor', () => {
  const base = { windowId: 'main', visible: true, symbol: 'PFSA', pane: { x: 0, y: 0, w: 10, h: 10 }, content: { x: 0, y: 0, width: 10, height: 10 }, inner: { w: 10, h: 10 }, panels: {}, minimized: false, displayId: 'd' };
  it('finds the tab shown, in the window it was shown in first', () => {
    const s = stateFor('PFSA', [{ ...base, windowId: 'trader:PFSA' }, base], 'main');
    expect(s).toMatchObject({ shown: true, windowId: 'main' });
  });
  it('says why a tab is not showing', () => {
    expect(stateFor('PFSA', [{ ...base, symbol: 'APUS' }], 'main')).toMatchObject({ shown: false, reason: 'symbol', showing: 'APUS' });
    expect(stateFor('PFSA', [{ ...base, minimized: true }], 'main')).toMatchObject({ shown: false, reason: 'minimized' });
    expect(stateFor('PFSA', [{ ...base, visible: false, reason: 'page' }], 'main')).toMatchObject({ shown: false, reason: 'page' });
    expect(stateFor('PFSA', [], 'main')).toMatchObject({ shown: false, reason: 'closed' });
    expect(stateFor('PFSA', [], null)).toMatchObject({ shown: false, reason: 'not_open' });
  });
});

describe('createTabTracker', () => {
  it('remembers the last half hour, so the last 5 minutes start where the tab was', () => {
    let t = 1_000_000;
    const tracker = createTabTracker({ screen, now: () => t });
    const win = fakeWindow(7);
    expect(tracker.report(win, report())).toBe(true);
    expect(tracker.report(win, report())).toBe(false);
    t += 60_000;
    tracker.report(win, report({ symbol: 'APUS' }));
    t += 30_000;
    tracker.report(win, report());
    const h = tracker.historyFor('PFSA', 1_000_000 / 1000 + 30);
    expect(h.map((s: { ts: number; shown: boolean; reason?: string }) => [s.ts, s.shown, s.reason ?? null])).toEqual([
      [1030, true, null],
      [1060, false, 'symbol'],
      [1090, true, null],
    ]);
    expect(h[0].geometry).toMatchObject({ window_id: 'main', display_id: '1449598500', pane: { x: 200, y: 90, w: 1200, h: 700 } });
  });

  it('reads a window again when it moves or minimizes', () => {
    const tracker = createTabTracker({ screen, now: () => 1 });
    const win = fakeWindow(9);
    tracker.report(win, report());
    win.minimize();
    expect(tracker.refresh(win)).toBe(true);
    expect(tracker.stateFor('PFSA', 'main')).toMatchObject({ shown: false, reason: 'minimized' });
    tracker.forget(9);
    expect(tracker.entries()).toEqual([]);
  });
});
