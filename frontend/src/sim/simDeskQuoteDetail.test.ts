/**
 * The quote a Sim desk may show, in the Trader tab's order (PR #868 review): the
 * loaded window's snapshot for its own symbol, nothing for any other symbol off
 * the live edge, the stream itself off Sim and at the edge.
 */
import { describe, expect, it } from 'vitest';
import { simDeskQuoteDetail } from './historicalQuoteDetail';
import type { SimClockState } from './simClockTypes';
import type { HistoricalSnapshot } from './useHistoricalSnapshot';
import type { TickerDetail } from '../types/ticker';

const live = {
  symbol: 'SUNE',
  asset: { name: 'SUNation Energy' },
  fundamentals: { float_shares: 4653225 },
  snapshot: { latest_trade: { price: 2.27, timestamp: '2026-10-12T21:55:56Z' }, prev_close: 2.28 },
} as unknown as TickerDetail;

const lnksLoaded = {
  live_edge: false, replay_ok: true, replay_loading: false,
  replay_source: 'historical', replay_symbol: 'LNKS', session_date: '2026-09-09',
} as unknown as SimClockState;

const lnksSnapshot = {
  active: true, symbol: 'LNKS', last: 1.42, as_of: '2026-09-09T12:03:02Z',
  session_open: null, high: 1.5, low: 1.3, volume: 9000, stats_scope: 'session', prev_close: 1.2,
} as unknown as HistoricalSnapshot;

describe('simDeskQuoteDetail', () => {
  it('passes the stream through off Sim and at the live edge', () => {
    expect(simDeskQuoteDetail(live, 'SUNE', false, lnksLoaded, null)).toBe(live);
    expect(simDeskQuoteDetail(live, 'SUNE', true, { ...lnksLoaded, live_edge: true }, null)).toBe(live);
  });

  it('shows no price for a symbol that is not the replay, keeping what is not a session price', () => {
    const shown = simDeskQuoteDetail(live, 'SUNE', true, lnksLoaded, null)!;
    expect(shown.snapshot?.latest_trade).toBeNull();
    expect(shown.snapshot?.prev_close).toBeNull();
    expect(shown.fundamentals).toBe(live.fundamentals);
  });

  it('shows the loaded window its own snapshot at the playhead', () => {
    const shown = simDeskQuoteDetail({ ...live, symbol: 'LNKS' }, 'LNKS', true, lnksLoaded, lnksSnapshot)!;
    expect(shown.snapshot?.latest_trade?.price).toBe(1.42);
    expect(shown.snapshot?.prev_close).toBe(1.2);
  });

  it('states nothing while the loaded window has no snapshot yet, never the live price', () => {
    const shown = simDeskQuoteDetail({ ...live, symbol: 'LNKS' }, 'LNKS', true, lnksLoaded, null)!;
    expect(shown.snapshot?.latest_trade).toBeNull();
  });

  it("shows a Session Record's quote for the recording's symbol", () => {
    const recording = {
      ...lnksLoaded, replay_source: 'capture', replay_symbol: 'SUNE',
      replay_quote: { covered: true, last: 3.02, bid: 3.01, ask: 3.03, ts: 1788956580, prev_close: 2.37 },
    } as unknown as SimClockState;
    const shown = simDeskQuoteDetail(live, 'sune', true, recording, null)!;
    expect(shown.snapshot?.latest_trade?.price).toBe(3.02);
    expect(shown.snapshot?.prev_close).toBe(2.37);
  });
});
