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

  // 2026-07-15 07:20 ET: Sim replaying a Massive-rebuilt day, GRML loaded (operator report, 2026-10-12).
  const minute = Date.UTC(2026, 6, 15, 11, 20) / 1000;
  const replay = {
    session_date: '2026-07-15', at: minute + 26, minute_ts: minute, board_source: 'reconstructed',
    board: 'market', board_rank: 98, rvol: 1.31, rvol_basis: 'time_of_day_20', absent: null,
  };

  it("names the replayed day's board row a replay desk graded, never a Contenders rank", async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ symbol: 'GRML', source: 'replay', rank: null, entry: entry('GRML', false), replay }),
    })));
    render(<TickerWatchlistStrip entry={null} symbol="GRML" />);
    await flush();
    expect(screen.getByTestId('watchlist-strip-source').textContent)
      .toBe('Jul 15 07:20 ET · graded from its rebuilt Gainers row (#98)');
    expect(screen.queryByText(/of the Contenders/)).toBeNull();
  });

  it('says why a replayed symbol has no grade instead of grading today', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        symbol: 'GRML', source: 'replay', rank: null, entry: null,
        replay: { ...replay, board: null, board_rank: null, absent: 'not_on_board' },
      }),
    })));
    render(<TickerWatchlistStrip entry={null} symbol="GRML" />);
    await flush();
    expect(screen.getByTestId('watchlist-strip-empty').textContent).toBe(
      "GRML is not on the Jul 15 07:20 ET board: nothing of that day to grade. Today's pillars are not shown on a replay.",
    );
    expect(screen.queryByTestId('watchlist-strip-source')).toBeNull();
  });

  it('names the gap when the replayed minute has no board', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        symbol: 'GRML', source: 'replay', rank: null, entry: null,
        replay: { ...replay, minute_ts: null, at: minute, board: null, board_rank: null, absent: 'not_recorded' },
      }),
    })));
    render(<TickerWatchlistStrip entry={null} symbol="GRML" />);
    await flush();
    expect(screen.getByTestId('watchlist-strip-empty').textContent)
      .toBe('No board at Jul 15 07:20 ET (not recorded): nothing of that day to grade.');
  });

  it('states a failed grade instead of an empty strip', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 503, json: async () => ({}) })));
    render(<TickerWatchlistStrip entry={null} symbol="NOPE" />);
    await flush();
    expect(screen.getByText(/Five Pillars: HTTP 503/)).toBeTruthy();
  });
});
