/**
 * @vitest-environment jsdom
 *
 * The account snapshot belongs to a venue (#657): after a switch Live never
 * shows Paper's orders or positions, not even as "last known".
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  _resetIbkrAccountPollerForTests,
  configureIbkrAccountPoller,
  getIbkrAccountSnapshot,
  subscribeIbkrAccount,
} from './ibkrAccountPoller';
import { _resetDeskPollShareForTests } from './deskSharedPoll';

let desk = 'paper';
let held: (() => void) | null = null;

function answer(url: string) {
  const rows = desk === 'paper'
    ? { positions: [{ symbol: 'PAPR', qty: 5 }], orders: [{ order_id: 12, symbol: 'PAPR', side: 'SELL', qty: 5 }] }
    : { positions: [], orders: [] };
  if (url.includes('/account')) return { connected: true, mode: desk, NetLiquidation: 1 };
  if (url.includes('/positions')) return rows.positions;
  if (url.includes('/orders/closed')) return [];
  if (url.includes('/orders')) return rows.orders;
  return [];
}

async function settle(): Promise<void> {
  for (let i = 0; i < 20; i += 1) await Promise.resolve();
}

describe('ibkrAccountPoller venue', () => {
  beforeEach(() => {
    desk = 'paper';
    held = null;
    _resetDeskPollShareForTests();
    _resetIbkrAccountPollerForTests();
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (held) await new Promise<void>((resolve) => { const prev = held; held = () => { prev?.(); resolve(); }; });
      return { ok: true, json: async () => answer(String(url)) };
    }));
  });

  afterEach(() => {
    _resetIbkrAccountPollerForTests();
    _resetDeskPollShareForTests();
    vi.unstubAllGlobals();
  });

  it('clears the old venue and reads the new one when the desk moves', async () => {
    configureIbkrAccountPoller({ connected: true, sample: false, venue: 'paper' });
    const off = subscribeIbkrAccount(() => {});
    await settle();
    expect(getIbkrAccountSnapshot().positions.map((p) => p.symbol)).toEqual(['PAPR']);
    expect(getIbkrAccountSnapshot().venue).toBe('paper');

    desk = 'live';
    configureIbkrAccountPoller({ connected: true, sample: false, venue: 'live' });
    expect(getIbkrAccountSnapshot().positions).toEqual([]);   // at once, before any read
    expect(getIbkrAccountSnapshot().orders).toEqual([]);
    expect(getIbkrAccountSnapshot().venue).toBe('live');
    await settle();
    expect(getIbkrAccountSnapshot().positions).toEqual([]);
    off();
  });

  it('drops a read that finishes after the switch', async () => {
    configureIbkrAccountPoller({ connected: true, sample: false, venue: 'paper' });
    held = () => {};                                          // hold the first reads
    const off = subscribeIbkrAccount(() => {});
    await settle();
    configureIbkrAccountPoller({ connected: true, sample: false, venue: 'live' });
    desk = 'paper';                                           // the held reads answer with Paper's rows
    const release = held;
    held = null;
    release?.();
    await settle();
    expect(getIbkrAccountSnapshot().venue).toBe('live');
    expect(getIbkrAccountSnapshot().positions.map((p) => p.symbol)).not.toContain('PAPR');
    off();
  });

  it('never shows the old venue as "last known" when the new one is disconnected', async () => {
    configureIbkrAccountPoller({ connected: true, sample: false, venue: 'paper' });
    const off = subscribeIbkrAccount(() => {});
    await settle();
    configureIbkrAccountPoller({ connected: false, sample: false, venue: 'live' });
    expect(getIbkrAccountSnapshot().positions).toEqual([]);
    expect(getIbkrAccountSnapshot().stale).toBe(false);
    off();
  });
});
