/**
 * Operator report (2026-10-09): every Trader chart on Sim at the live edge sat
 * on "Loading…". The backend serves live bars there, as it does Paper; the bars
 * store read every Sim tab as a replay and threw them away.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const clock = vi.hoisted(() => ({ data: null as null | { live_edge?: boolean } }));

vi.mock('../ibkr/ibkrStatusPoller', () => ({ getIbkrStatusSnapshot: () => ({ mode: 'sim' }) }));
vi.mock('../sim', () => ({
  simClockResource: { getSnapshot: () => ({ data: clock.data, error: null }), subscribe: () => () => {} },
}));

import { clearBarsStoreForTests, ensureBars, getBarsEntry, upsertTapePrint10SecBar } from './barsStore';
import { simChartReplays } from './simChartReplays';

const LIVE_BAR = { t: '2026-10-09T22:05:00Z', o: 9.04, h: 9.08, l: 9.03, c: 9.05, v: 3409 };
const liveAnswer = { ok: true, json: async () => ({ bars: [LIVE_BAR], coverage: { filling: false } }) };

beforeEach(() => {
  clearBarsStoreForTests();
  vi.stubGlobal('fetch', vi.fn(async () => liveAnswer));
});
afterEach(() => {
  vi.unstubAllGlobals();
  clearBarsStoreForTests();
  clock.data = null;
});

describe('simChartReplays', () => {
  it('gives a Sim pane to the replay off the edge and before the clock answers, never at the edge', () => {
    expect(simChartReplays(false, null)).toBe(false);
    expect(simChartReplays(false, { live_edge: false })).toBe(false);
    expect(simChartReplays(true, null)).toBe(true);
    expect(simChartReplays(true, { live_edge: false })).toBe(true);
    expect(simChartReplays(true, {})).toBe(true);
    expect(simChartReplays(true, { live_edge: true })).toBe(false);
  });
});

describe('the bars store on Sim', () => {
  it('takes the live bars at the live edge', async () => {
    clock.data = { live_edge: true };
    await expect(ensureBars('WFF', '1Min')).resolves.toEqual([LIVE_BAR]);
    expect(getBarsEntry('WFF', '1Min')?.bars).toEqual([LIVE_BAR]);
  });

  it('still refuses a live answer off the edge', async () => {
    clock.data = { live_edge: false };
    await expect(ensureBars('WFF', '1Min')).rejects.toMatchObject({ name: 'AbortError' });
    expect(getBarsEntry('WFF', '1Min')).toBeNull();
  });

  it('lets live prints build the 10-second candle at the edge, and only there', () => {
    const print = { time: '2026-10-09T22:05:41Z', price: 9.07, size: 100 };
    clock.data = { live_edge: false };
    expect(upsertTapePrint10SecBar('WFF', print)).toBe(false);
    clock.data = { live_edge: true };
    expect(upsertTapePrint10SecBar('WFF', print)).toBe(true);
    expect(getBarsEntry('WFF', '10Sec')?.bars.at(-1)).toMatchObject({ c: 9.07, v: 100 });
  });
});
