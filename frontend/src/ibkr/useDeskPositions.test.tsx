/** @vitest-environment jsdom */
import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { PracticeAccount } from '../practice';
import type { IbkrPosition } from './types';
import { useBotsQty, useDeskPositions } from './useDeskPositions';

const read = vi.hoisted(() => ({
  venue: 'paper' as string | null,
  sampleRoute: false,
  sampleData: null as object | null,
  practice: { data: null as PracticeAccount | null, error: null as string | null, stale: false },
  asked: [] as (string | null | undefined)[],
}));

vi.mock('../practice', () => ({
  usePracticeAccount: (venue: string | null | undefined) => {
    read.asked.push(venue);
    return venue ? read.practice : { data: null, error: null };
  },
}));
vi.mock('./useIbkrStatus', () => ({ useIbkrStatus: () => ({ venue: read.venue, mode: read.venue }) }));
vi.mock('../sample_data/SampleDataContext', () => ({ useSampleDataOptional: () => read.sampleData }));
vi.mock('../sample_data/useSampleRoute', () => ({ useSampleRoute: () => read.sampleRoute }));

const account = {
  books: {},
  positions: [{
    symbol: 'ORCL', qty: -19, avg_cost: 125.9, mark: 124.89, unrealized: 19.19,
    by_owner: [{ owner: 'bots', bot: 'live_trader', qty: -19, avg_cost: 125.9, unrealized_pnl: 19.19 }],
  }],
} as unknown as PracticeAccount;

const MINE: IbkrPosition[] = [{
  symbol: 'INTC', qty: 100, avg_cost: 58, market_price: 58, market_value: 5800, unrealized_pnl: 0, realized_pnl: 0,
}];

beforeEach(() => {
  read.venue = 'paper';
  read.sampleRoute = false;
  read.sampleData = null;
  read.practice = { data: account, error: null, stale: false };
  read.asked = [];
});

describe('useDeskPositions', () => {
  it("adds the bots' rows on Paper", () => {
    const { result } = renderHook(() => useDeskPositions(MINE));
    expect(result.current.rows.map((r) => [r.symbol, r.owner])).toEqual([['INTC', 'you'], ['ORCL', 'bots']]);
    expect(result.current.split).toBe(true);
    expect(result.current.botsBook.get('ORCL')).toBe(-19);
  });

  it.each(['live', 'sim', null])('asks for nothing on %s and hands your rows back', (venue) => {
    read.venue = venue;
    const { result } = renderHook(() => useDeskPositions(MINE));
    expect(result.current.rows).toBe(MINE);
    expect(result.current.split).toBe(false);
    expect(read.asked.every((v) => v == null)).toBe(true);
  });

  it('asks for nothing on the sample desk, by its route or its provider', () => {
    read.sampleRoute = true;
    expect(renderHook(() => useDeskPositions(MINE)).result.current.rows).toBe(MINE);
    read.sampleRoute = false;
    read.sampleData = {};
    expect(renderHook(() => useDeskPositions(MINE)).result.current.rows).toBe(MINE);
    expect(read.asked.every((v) => v == null)).toBe(true);
  });

  it('says so when the read of the bots\' shares fails', () => {
    read.practice = { data: null, error: 'Practice account request failed', stale: false };
    expect(renderHook(() => useDeskPositions(MINE)).result.current.botsStale).toBe(true);
    read.practice = { data: account, error: null, stale: true };
    expect(renderHook(() => useDeskPositions(MINE)).result.current.botsStale).toBe(true);
  });
});

describe('useBotsQty', () => {
  it("reads the bots' shares in one stock, signed, whatever the case", () => {
    expect(renderHook(() => useBotsQty(' orcl ')).result.current).toBe(-19);
    expect(renderHook(() => useBotsQty('INTC')).result.current).toBe(0);
    expect(renderHook(() => useBotsQty(null)).result.current).toBe(0);
  });
});
