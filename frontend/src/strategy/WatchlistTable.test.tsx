/**
 * @vitest-environment jsdom
 */
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { SAMPLE_SETUPS_BOARD } from '../sample_data/sampleSetups';
import { WatchlistTable } from './WatchlistTable';
import type { WatchlistEntry } from './types';

const add = vi.fn();
const remove = vi.fn();
const allowlist = new Set(['QMBL']);
vi.mock('../bot/useBotAllowlist', () => ({
  useBotAllowlist: () => ({
    symbols: [...allowlist],
    isAllowed: (s: string) => allowlist.has(s),
    add,
    remove,
    refresh: vi.fn(),
  }),
}));
vi.mock('../setups/SetupsStreamContext', () => ({
  useSetupsBoard: () => ({ board: SAMPLE_SETUPS_BOARD, connected: true }),
}));

const PILLARS = ['price', 'change_pct', 'relative_volume', 'catalyst', 'float'];

function entry(symbol: string, passing: number, extra: Partial<WatchlistEntry> = {}): WatchlistEntry {
  return {
    symbol,
    composite_score: 40 + passing * 10,
    sub_scores: { change_pct: 50, relative_volume: 50, float: 50, catalyst: 50 },
    five_pillars: {
      symbol,
      all_pass: passing === 5,
      pass_count: passing,
      total: 5,
      checkmark: passing === 5 ? '✓' : '',
      pillars: PILLARS.map((name, i) => ({ name, passed: i < passing, detail: `${name} detail` })),
    },
    price: 4.35,
    change_pct: 0.427,
    rel_volume: 18.2,
    rvol_source: 'yfinance',
    float_shares: 3_100_000,
    has_news: true,
    catalyst: null,
    ...extra,
  };
}

const ENTRIES = [
  entry('NVXA', 5, {
    catalyst: { verdict: 'catalyst', category: 'fda_regulatory', strength: 'strong', title: 'FDA clears',
      source: 'globenewswire', published_ts: 1_790_000_000, news_pending: false },
  }),
  entry('QMBL', 4, { has_news: false }),
  entry('ZZZZ', 3, { price: null, change_pct: null, rel_volume: null, float_shares: null }),
];

function renderTable() {
  return render(
    <WatchlistTable
      entries={ENTRIES}
      loading={false}
      error={null}
      selectedSymbol={null}
      onSelectSymbol={vi.fn()}
      onOpenTrading={vi.fn()}
    />,
  );
}

function rowOf(symbol: string): HTMLElement {
  return screen.getAllByRole('row').find(r => within(r).queryByText(symbol, { selector: 'button' }))!;
}

afterEach(() => {
  cleanup();
  add.mockReset();
  remove.mockReset();
});

describe('WatchlistTable', () => {
  it('shows the market columns, the catalyst and the setup state per row', () => {
    renderTable();
    const nvxa = within(rowOf('NVXA'));
    expect(nvxa.getByText('5/5')).toBeTruthy();
    expect(nvxa.getByText('4.35')).toBeTruthy();
    expect(nvxa.getByText('+42.70%')).toBeTruthy();
    expect(nvxa.getByText('18.2x')).toBeTruthy();
    expect(nvxa.getByText('3.1M')).toBeTruthy();
    expect(nvxa.getByText('FDA')).toBeTruthy();
    expect(nvxa.getByText('Near · 4.37')).toBeTruthy();
    expect(within(rowOf('QMBL')).getByText('Armed · 7.12')).toBeTruthy();
  });

  it('states unknowns instead of inventing them', () => {
    renderTable();
    const zzzz = within(rowOf('ZZZZ'));
    // Last, % Chg, RVOL, Float, News and Setup are all unknown for this row.
    expect(zzzz.getAllByText('—').length).toBeGreaterThanOrEqual(5);
    expect(zzzz.getByText('Article')).toBeTruthy(); // an article exists, no catalyst read yet
  });

  it('summarizes and filters without refetching', () => {
    renderTable();
    const summary = screen.getByTestId('watchlist-summary').textContent ?? '';
    expect(summary).toContain('3 gappers & gainers');
    expect(summary).toContain('1 pass all five pillars');
    expect(summary).toContain('2 setups live · 1 near trigger');
    expect(summary).toContain('1 on the bot allowlist');

    fireEvent.click(screen.getByText('5/5 pillars'));
    expect(screen.queryByText('QMBL', { selector: 'button' })).toBeNull();
    fireEvent.click(screen.getByText('On bot allowlist'));
    expect(screen.getByText('QMBL', { selector: 'button' })).toBeTruthy();
    expect(screen.queryByText('NVXA', { selector: 'button' })).toBeNull();
  });

  it('toggles the bot allowlist from the dot', () => {
    renderTable();
    fireEvent.click(within(rowOf('NVXA')).getByTestId('watchlist-bot-toggle'));
    expect(add).toHaveBeenCalledWith('NVXA');
    fireEvent.click(within(rowOf('QMBL')).getByTestId('watchlist-bot-toggle'));
    expect(remove).toHaveBeenCalledWith('QMBL');
  });
});
