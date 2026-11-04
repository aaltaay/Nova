/**
 * @vitest-environment jsdom
 *
 * The Reports tab follows the Account page's venue and its All / You / Bots pick (ADR 069 decision 6, mockup
 * reports-v1): Paper asks for its round trips by the pick and shows yours and the bots' beside each total on All;
 * Live asks as before and keeps its Import row.
 */
import { act, cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REPORTS_IMPORT_ON_LIVE, REPORTS_SOURCE_NOTE_PAPER } from './booksConstants';
import { REPORTS_SOURCE_NOTE } from './importConstants';
import { ReportsTab } from './ReportsTab';

const books = (you: number, bots: number, youN = 1, botsN = 1) => ({
  you: { pnl: you, trade_count: youN },
  bots: { pnl: bots, trade_count: botsN },
});

const YEAR = {
  year: 2026, timezone: 'America/New_York', includes_mock_data: false,
  year_pnl: -20, year_trade_count: 3, winning_days: 1, losing_days: 1, flat_days: 0,
  best_day: { date: '2026-10-30', pnl: 30, trade_count: 1, by_owner: books(0, 30, 0, 1) },
  worst_day: { date: '2026-10-15', pnl: -50, trade_count: 2, by_owner: books(-50, 0, 2, 0) },
  months: [{ year: 2026, month: 10, pnl: -20, trade_count: 3, winning_days: 1, losing_days: 1, flat_days: 0,
    days: [], by_owner: books(-50, 30, 2, 1) }],
  by_owner: books(-50, 30, 2, 1),
  holders: [{ owner: 'you', bot: null, trade_count: 2 }, { owner: 'bots', bot: 'live_trader', trade_count: 1 }],
};
const R = {
  includes_mock_data: false, trade_count: 3, scored_count: 1, skipped_no_stop: 2, expectancy_r: 0.5,
  avg_win_r: 0.5, avg_loss_r: null, trades: [],
  by_owner: {
    you: { trade_count: 2, scored_count: 0, skipped_no_stop: 2, expectancy_r: null, avg_win_r: null, avg_loss_r: null },
    bots: { trade_count: 1, scored_count: 1, skipped_no_stop: 0, expectancy_r: 0.5, avg_win_r: 0.5, avg_loss_r: null },
  },
};
const DD = {
  includes_mock_data: false, trade_count: 3, final_equity: -20, peak_equity: 0, max_drawdown: 50,
  max_drawdown_pct: null,
  curve: [
    { trade_id: 1, symbol: 'AAA', closed_ts: 1, pnl: -25, equity: -25, drawdown: 25, owner: 'you', bot: null },
    { trade_id: 2, symbol: 'BBB', closed_ts: 2, pnl: -25, equity: -50, drawdown: 50, owner: 'you', bot: null },
    { trade_id: 3, symbol: 'CCC', closed_ts: 3, pnl: 30, equity: -20, drawdown: 20, owner: 'bots', bot: 'live_trader' },
  ],
};

function answer(url: string) {
  if (url.includes('/calendar')) return YEAR;
  if (url.includes('/r-multiples')) return R;
  if (url.includes('/drawdown')) return DD;
  return { includes_mock_data: false, count: 0, tags: [] };
}

function stubFetch() {
  const fetch = vi.fn(async (url: string) => ({ ok: true, json: async () => answer(url) }));
  vi.stubGlobal('fetch', fetch);
  return fetch;
}

async function settle() {
  await act(async () => {
    for (let i = 0; i < 20; i += 1) await Promise.resolve();
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('ReportsTab on Paper', () => {
  it('asks for Paper by the pick and says where its trades come from', async () => {
    const fetch = stubFetch();
    const onBotCounts = vi.fn();
    render(<ReportsTab venue="paper" view={{ book: 'all', bot: null }} onBotCounts={onBotCounts} />);
    await settle();
    const urls = fetch.mock.calls.map(([url]) => String(url));
    expect(urls.length).toBeGreaterThan(0);
    expect(urls.every((u) => u.includes('venue=paper'))).toBe(true);
    expect(screen.getByTestId('reports-source-note').textContent).toBe(REPORTS_SOURCE_NOTE_PAPER);
    expect(screen.getByTestId('reports-import-on-live').textContent).toBe(REPORTS_IMPORT_ON_LIVE);
    expect(onBotCounts).toHaveBeenLastCalledWith({ all: 1, byBot: { live_trader: 1 } });
  });

  it('shows yours and the bots beside each total on All', async () => {
    stubFetch();
    render(<ReportsTab venue="paper" view={{ book: 'all', bot: null }} />);
    await settle();
    const splits = screen.getAllByTestId('reports-split');
    expect(splits.length).toBeGreaterThan(4);
    const yearPnl = splits[0];
    expect(within(yearPnl).getByTestId('reports-split-you').textContent).toContain('-$50.00');
    expect(within(yearPnl).getByTestId('reports-split-bots').textContent).toContain('$30.00');
    expect(within(yearPnl).getByTestId('reports-split-you').className).toContain('pnl-neg');
    // The best day had no trade of yours: a dash, not $0.
    expect(within(splits[2]).getByTestId('reports-split-you').textContent).toContain('—');
    expect(screen.getByTestId('reports-r-hint').textContent)
      .toContain("2 of your 2 sent none, and 0 of the bots' 1.");
    const bars = document.querySelectorAll('.reports-v2-curve-bar');
    expect([...bars].map((b) => b.className)).toEqual([
      'reports-v2-curve-bar is-you', 'reports-v2-curve-bar is-you', 'reports-v2-curve-bar is-bots',
    ]);
  });

  it('asks for one bot alone', async () => {
    const fetch = stubFetch();
    render(<ReportsTab venue="paper" view={{ book: 'bots', bot: 'claude' }} />);
    await settle();
    expect(String(fetch.mock.calls[0][0])).toContain('venue=paper&owner=bots&bot=claude');
  });
});

describe('ReportsTab on Live', () => {
  it('asks as before and keeps its Import row', async () => {
    const fetch = stubFetch();
    const onBotCounts = vi.fn();
    render(<ReportsTab venue="live" view={{ book: 'all', bot: null }} onBotCounts={onBotCounts} />);
    await settle();
    expect(fetch.mock.calls.every(([url]) => !String(url).includes('venue='))).toBe(true);
    expect(screen.getByTestId('reports-source-note').textContent).toBe(REPORTS_SOURCE_NOTE);
    expect(screen.queryByTestId('reports-import-on-live')).toBeNull();
    expect(onBotCounts).toHaveBeenLastCalledWith(null);
  });
});
