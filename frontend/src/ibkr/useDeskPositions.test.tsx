/** @vitest-environment jsdom */
import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { PracticeAccount } from '../practice';
import type { IbkrPosition } from './types';
import { useDeskPositions, useOthersHold } from './useDeskPositions';

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
    by_owner: [{ owner: 'claude', bot: null, qty: -19, avg_cost: 125.9, unrealized_pnl: 19.19, handed: false }],
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

describe('useDeskPositions (ADR 072)', () => {
  it.each(['paper', 'sim'])("adds the other traders' rows on %s", (venue) => {
    read.venue = venue;
    const { result } = renderHook(() => useDeskPositions(MINE));
    expect(result.current.rows.map((r) => [r.symbol, r.owner])).toEqual([['INTC', 'you'], ['ORCL', 'claude']]);
    expect(result.current.split).toBe(true);
    expect(result.current.othersBook.get('ORCL')).toEqual([{ owner: 'claude', qty: -19 }]);
    expect(read.asked).toContain(venue);
  });

  it.each(['live', null])('asks for nothing on %s and hands your rows back', (venue) => {
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

  it("says so when the read of the other traders' shares fails", () => {
    read.practice = { data: null, error: 'Practice account request failed', stale: false };
    expect(renderHook(() => useDeskPositions(MINE)).result.current.othersStale).toBe(true);
    read.practice = { data: account, error: null, stale: true };
    expect(renderHook(() => useDeskPositions(MINE)).result.current.othersStale).toBe(true);
  });
});

describe('useOthersHold', () => {
  it('reads the other trader in one stock and its shares, signed, whatever the case', () => {
    expect(renderHook(() => useOthersHold(' orcl ')).result.current).toEqual({ owner: 'claude', qty: -19 });
    expect(renderHook(() => useOthersHold('INTC')).result.current).toBeNull();
    expect(renderHook(() => useOthersHold(null)).result.current).toBeNull();
  });
});
