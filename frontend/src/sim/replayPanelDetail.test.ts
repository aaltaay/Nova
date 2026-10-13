/**
 * The scanner quote panel's detail on a Sim desk (operator report, 2026-10-12): the replayed
 * moment, or a stated absence -- never today's company figures as that day's.
 */
import { describe, expect, it } from 'vitest';
import type { FundamentalsData, TickerDetail } from '../types/ticker';
import { replayCompanyFacts, replayPanelDetail, splitDate } from './replayPanelDetail';
import type { SimClockState } from './simClockTypes';

const facts = {
  country: 'United States', country_code: 'US', sector: 'Basic Materials', industry: 'Other Precious Metals',
  float_shares: 3_075_412, short_interest: 935_276, market_cap: 80_349_736, fifty_two_week_high: 37,
  recent_split: '1:50 (2026-08-24)',
} as unknown as FundamentalsData;
const detail = { symbol: 'GRML', fundamentals: facts, asset: {}, snapshot: {} } as unknown as TickerDetail;
const pastDay = {
  live_edge: false, replay_ok: true, replay_loading: false, replay_source: 'historical',
  replay_symbol: 'KUST', session_date: '2026-07-15',
} as unknown as SimClockState;

describe('replayCompanyFacts', () => {
  it('keeps who the company is and drops every figure Nova holds only for today', () => {
    const kept = replayCompanyFacts(facts, '2026-07-15')!;
    expect(kept).toMatchObject({ country: 'United States', country_code: 'US', sector: 'Basic Materials' });
    expect([kept.float_shares, kept.short_interest, kept.market_cap, kept.fifty_two_week_high]).toEqual([null, null, null, null]);
    // The split came after the replayed day: not that day's "recent split".
    expect(kept.recent_split).toBeNull();
  });

  it('keeps a split on or before the replayed day', () => {
    expect(replayCompanyFacts(facts, '2026-08-24')?.recent_split).toBe('1:50 (2026-08-24)');
    expect(splitDate('1:50 (2026-08-24)')).toBe('2026-08-24');
    expect(splitDate(null)).toBeNull();
  });
});

describe('replayPanelDetail', () => {
  it('passes the live detail through off Sim and at the live edge', () => {
    expect(replayPanelDetail(detail, 'GRML', null, false, null)).toEqual({ detail, note: null });
    const edge = { ...pastDay, live_edge: true } as SimClockState;
    expect(replayPanelDetail(detail, 'GRML', edge, true, null)).toEqual({ detail, note: null });
  });

  it('empties another symbol\'s quote off the edge and names a later split in the note', () => {
    const out = replayPanelDetail(detail, 'GRML', pastDay, true, null);
    expect(out.detail?.snapshot.latest_trade).toBeNull();
    expect(out.detail?.fundamentals?.float_shares).toBeNull();
    expect(out.note).toMatch(/^Replay of Jul 15: .* GRML split 1:50 \(2026-08-24\), after this day\.$/);
  });
});
