/**
 * @vitest-environment jsdom
 *
 * The quote panel's Five Pillars for any symbol (operator ask, 2026-09-23):
 * a ranked one from the watchlist poll, any other graded on demand by
 * GET /api/strategy/watchlist/{symbol}, and the source said out loud.
 */
import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { WatchlistEntry } from '../strategy/types';
import { TickerWatchlistStrip } from './TickerWatchlistStrip';

vi.mock('../setups/SetupsStreamContext', () => ({ useSetupsBoard: () => null }));
vi.mock('../bot/useBotAllowlist', () => ({
  useBotAllowlist: () => ({ isAllowed: () => false, add: vi.fn(), remove: vi.fn() }),
}));

function entry(symbol: string, passed = true): WatchlistEntry {
  const names = ['price', 'change_pct', 'relative_volume', 'catalyst', 'float'];
  return {
    symbol,
    composite_score: 70,
    sub_scores: { change_pct: 1, relative_volume: 1, float: 1, catalyst: 1 },
    five_pillars: {
      symbol, all_pass: passed, pass_count: passed ? 5 : 4, total: 5, checkmark: '',
      pillars: names.map((name, i) => ({ name, passed: passed || i > 0, detail: `${name} detail` })),
    },
    catalyst: null,
  };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function flush() {
  await act(async () => {
    for (let i = 0; i < 6; i += 1) await Promise.resolve();
  });
}

describe('TickerWatchlistStrip', () => {
  it('uses the ranked entry without asking the backend, and says its rank', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    render(<TickerWatchlistStrip entry={entry('GRML')} symbol="GRML" rank={3} />);
    await flush();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByText(/5 \/ 5 pillars/)).toBeTruthy();
    expect(screen.getByTestId('watchlist-strip-source').textContent).toBe('#3 of the Contenders');
  });

  it('grades an unranked symbol on demand and says where the grade came from', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ symbol: 'WHLR', source: 'quote', rank: null, entry: entry('WHLR', false) }),
    }));
    vi.stubGlobal('fetch', fetchMock);
    render(<TickerWatchlistStrip entry={null} symbol="whlr" />);
    expect(screen.getByText('Grading the Five Pillars…')).toBeTruthy();
    await flush();
    expect(String((fetchMock.mock.calls[0] as unknown[])[0])).toMatch(/\/api\/strategy\/watchlist\/WHLR$/);
    expect(screen.getByText(/4 \/ 5 pillars/)).toBeTruthy();
    expect(screen.getByTestId('watchlist-strip-source').textContent).toBe('Not on a board · graded from its live quote');
    expect(screen.getByText('price detail')).toBeTruthy();
  });

  it('states a failed grade instead of an empty strip', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 503, json: async () => ({}) })));
    render(<TickerWatchlistStrip entry={null} symbol="NOPE" />);
    await flush();
    expect(screen.getByText(/Five Pillars: HTTP 503/)).toBeTruthy();
  });
});
