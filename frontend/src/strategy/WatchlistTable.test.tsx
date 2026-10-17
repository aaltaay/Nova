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
    // ADR 031: the symbol's most advanced setup, named.
    expect(nvxa.getByText('First pullback · Near · 4.37')).toBeTruthy();
    expect(within(rowOf('QMBL')).getByText('First pullback · Armed · 7.12')).toBeTruthy();
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
    expect(summary).toContain('1 set to Bot');

    fireEvent.click(screen.getByText('5/5 pillars'));
    expect(screen.queryByText('QMBL', { selector: 'button' })).toBeNull();
    fireEvent.click(screen.getByText('Bot trades it'));
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

  it('renders replay provenance and distinguishes reconstructed rows, covered empty boards, missing coverage, loading and errors (#881)', () => {
    const replayEntry = entry('GRML', 0, {
      price: 0.1875,
      change_pct: 0.0411,
      rel_volume: null,
      rvol_source: null,
      float_shares: null,
      has_news: false,
      five_pillars: {
        symbol: 'GRML',
        all_pass: false,
        pass_count: 0,
        total: 5,
        checkmark: '0/5',
        pillars: [
          { name: 'price', passed: false, detail: '$0.19 (need $2-$20)' },
          { name: 'change_pct', passed: false, detail: '4.1% (need >= 10%)' },
          {
            name: 'relative_volume',
            passed: false,
            detail: "daily RVOL unknown -- 1.3x the same minute's 20-day average is another measure, not graded",
          },
          { name: 'catalyst', passed: false, detail: 'no news or technical breakout' },
          { name: 'float', passed: false, detail: 'float unknown' },
        ],
      },
    });
    const replayMeta = {
      session_date: '2026-07-15',
      at: 1_752_578_426,
      minute_ts: 1_752_578_400,
      board_source: 'reconstructed' as const,
      covered: true,
      absent: null,
    };

    const { rerender } = render(
      <WatchlistTable
        entries={[replayEntry]}
        loading={false}
        error={null}
        replay={replayMeta}
        selectedSymbol={null}
        onSelectSymbol={vi.fn()}
        onOpenTrading={vi.fn()}
      />,
    );
    const prov = screen.getByTestId('watchlist-replay-provenance').textContent ?? '';
    expect(prov).toContain('2026-07-15');
    expect(prov).toContain('Jul 15 07:20 ET');
    expect(prov).toContain('reconstructed');
    const grml = within(rowOf('GRML'));
    expect(grml.getByText('0.1875')).toBeTruthy();
    expect(grml.getAllByTitle(/daily RVOL unknown -- 1\.3x/).length).toBe(2);
    expect(grml.getAllByTitle('float unknown').length).toBe(2);

    // Covered empty board:
    rerender(
      <WatchlistTable
        entries={[]}
        loading={false}
        error={null}
        replay={replayMeta}
        selectedSymbol={null}
        onSelectSymbol={vi.fn()}
        onOpenTrading={vi.fn()}
      />,
    );
    expect(screen.getByText(/No candidates on the Jul 15 07:20 ET \(2026-07-15\) reconstructed board/i)).toBeTruthy();

    // Missing board coverage:
    rerender(
      <WatchlistTable
        entries={[]}
        loading={false}
        error={null}
        replay={{ ...replayMeta, covered: false, absent: 'not_recorded' }}
        selectedSymbol={null}
        onSelectSymbol={vi.fn()}
        onOpenTrading={vi.fn()}
      />,
    );
    expect(screen.getByText(/Historical Contenders ranking unavailable at Jul 15 07:20 ET \(2026-07-15\).*not recorded/i)).toBeTruthy();

    // Loading state:
    rerender(
      <WatchlistTable
        entries={[]}
        loading
        error={null}
        replay={replayMeta}
        selectedSymbol={null}
        onSelectSymbol={vi.fn()}
        onOpenTrading={vi.fn()}
      />,
    );
    expect(screen.getByText('Loading Contenders…')).toBeTruthy();

    // Read failure state:
    rerender(
      <WatchlistTable
        entries={[]}
        loading={false}
        error="HTTP 503"
        replay={null}
        selectedSymbol={null}
        onSelectSymbol={vi.fn()}
        onOpenTrading={vi.fn()}
      />,
    );
    expect(screen.getByText('HTTP 503')).toBeTruthy();
  });
});
