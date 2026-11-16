/**
 * @vitest-environment jsdom
 *
 * The Reports tab follows the Account page's venue and its All / You / Claude / The brain / Earlier bots pick (ADR
 * 072, mockup three-books v1 "Account › Reports"): Paper asks for its round trips by the pick, counts each pick's
 * closed trades for the switch, and lists the four books beside each total on All -- a day only the traders who
 * traded it. Live asks as before and keeps its Import row.
 */
import { act, cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REPORTS_IMPORT_ON_LIVE, REPORTS_SOURCE_NOTE_PAPER } from './booksConstants';
import { REPORTS_SOURCE_NOTE } from './importConstants';
import { MonthDetail } from './MonthDetail';
import { ReportsTab } from './ReportsTab';
import type { MonthCalendarResponse } from './types';

type Sums = [pnl: number, trades: number];
const books = (you: Sums, claude: Sums = [0, 0], brain: Sums = [0, 0], earlier: Sums = [0, 0]) => ({
  you: { pnl: you[0], trade_count: you[1] },
  claude: { pnl: claude[0], trade_count: claude[1] },
  brain: { pnl: brain[0], trade_count: brain[1] },
  earlier_bots: { pnl: earlier[0], trade_count: earlier[1] },
});

const YEAR = {
  year: 2026, timezone: 'America/New_York', includes_mock_data: false,
  year_pnl: -20, year_trade_count: 4, winning_days: 1, losing_days: 1, flat_days: 0,
  best_day: { date: '2026-10-30', pnl: 30, trade_count: 1, by_owner: books([0, 0], [0, 0], [0, 0], [30, 1]) },
  worst_day: { date: '2026-10-15', pnl: -50, trade_count: 2, by_owner: books([-50, 2]) },
  months: [{ year: 2026, month: 10, pnl: -20, trade_count: 4, winning_days: 1, losing_days: 1, flat_days: 0,
    days: [], by_owner: books([-50, 2], [0, 1], [0, 0], [30, 1]) }],
  by_owner: books([-50, 2], [0, 1], [0, 0], [30, 1]),
  holders: [
    { owner: 'you', bot: null, trade_count: 2 },
    { owner: 'claude', bot: null, trade_count: 1 },
    { owner: 'earlier_bots', bot: 'live_trader', trade_count: 1 },
  ],
};
const rBook = (n: number, skipped: number, r: number | null) => ({
  trade_count: n, scored_count: n - skipped, skipped_no_stop: skipped, expectancy_r: r, avg_win_r: r, avg_loss_r: null,
});
const R = {
  includes_mock_data: false, trade_count: 4, scored_count: 2, skipped_no_stop: 2, expectancy_r: 0.5,
  avg_win_r: 0.5, avg_loss_r: null, trades: [],
  by_owner: { you: rBook(2, 2, null), claude: rBook(1, 0, 0.4), brain: rBook(0, 0, null), earlier_bots: rBook(1, 0, 0.6) },
};
const point = (id: number, equity: number, owner: string, bot: string | null = null) => ({
  trade_id: id, symbol: `S${id}`, closed_ts: id, pnl: 0, equity, drawdown: 0, owner, bot,
});
const DD = {
  includes_mock_data: false, trade_count: 4, final_equity: -20, peak_equity: 0, max_drawdown: 50,
  max_drawdown_pct: null,
  curve: [point(1, -25, 'you'), point(2, -50, 'you'), point(3, -50, 'claude'), point(4, -20, 'earlier_bots', 'live_trader')],
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

const partsOf = (split: HTMLElement) =>
  within(split).getAllByTestId(/^reports-split-/).map((p) => p.getAttribute('data-testid')?.replace('reports-split-', ''));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('ReportsTab on Paper', () => {
  it("asks for Paper by the pick, says where its trades come from, and counts each pick's closed trades", async () => {
    const fetch = stubFetch();
    const onBotCounts = vi.fn();
    render(<ReportsTab venue="paper" view={{ book: 'all', bot: null }} onBotCounts={onBotCounts} />);
    await settle();
    const urls = fetch.mock.calls.map(([url]) => String(url));
    expect(urls.length).toBeGreaterThan(0);
    expect(urls.every((u) => u.includes('venue=paper'))).toBe(true);
    expect(screen.getByTestId('reports-source-note').textContent).toBe(REPORTS_SOURCE_NOTE_PAPER);
    expect(screen.getByTestId('reports-import-on-live').textContent).toBe(REPORTS_IMPORT_ON_LIVE);
    expect(onBotCounts).toHaveBeenLastCalledWith({
      all: 1, byBot: { live_trader: 1 }, books: { you: 2, claude: 1, brain: 0, earlier_bots: 1 },
    });
  });

  it('lists all four books beside each year total, in order, in their colours', async () => {
    stubFetch();
    render(<ReportsTab venue="paper" view={{ book: 'all', bot: null }} />);
    await settle();
    const splits = screen.getAllByTestId('reports-split');
    expect(splits.length).toBeGreaterThan(4);
    const [yearPnl, trades] = splits;
    expect(partsOf(yearPnl)).toEqual(['you', 'claude', 'brain', 'earlier_bots']);
    expect(within(yearPnl).getByTestId('reports-split-you').textContent).toContain('-$50.00');
    expect(within(yearPnl).getByTestId('reports-split-you').className).toContain('pnl-neg');
    expect(within(yearPnl).getByTestId('reports-split-earlier_bots').textContent).toContain('$30.00');
    // A book with no trade this year still shows, at its $0 (the mockup's brain).
    expect(within(yearPnl).getByTestId('reports-split-brain').textContent).toContain('$0.00');
    expect(within(trades).getByTestId('reports-split-brain').textContent).toContain('0');
    const dot = (book: string) => within(yearPnl).getByTestId(`reports-split-${book}`).querySelector('i') as HTMLElement;
    expect(dot('claude').style.background).toBe('rgb(217, 119, 87)');      // OWNER_COLORS.claude
    expect(dot('brain').style.background).toBe('rgb(139, 92, 246)');       // OWNER_COLORS.brain
  });

  it('lists only the traders who traded the best and the worst day', async () => {
    stubFetch();
    render(<ReportsTab venue="paper" view={{ book: 'all', bot: null }} />);
    await settle();
    const [, , best, worst] = screen.getAllByTestId('reports-split');
    expect(partsOf(best)).toEqual(['earlier_bots']);
    expect(partsOf(worst)).toEqual(['you']);
  });

  it('says how many of each trading book sent no stop, and colours each bar by its book', async () => {
    stubFetch();
    render(<ReportsTab venue="paper" view={{ book: 'all', bot: null }} />);
    await settle();
    expect(screen.getByTestId('reports-r-hint').textContent)
      .toContain("2 of your 2, 0 of Claude's 1 and 0 of the earlier bots' 1 sent none.");
    const bars = [...document.querySelectorAll<SVGRectElement>('.reports-v2-curve-bar')];
    expect(bars.map((b) => b.getAttribute('class'))).toEqual([
      'reports-v2-curve-bar is-you', 'reports-v2-curve-bar is-you',
      'reports-v2-curve-bar is-claude', 'reports-v2-curve-bar is-earlier_bots',
    ]);
    expect(bars[2].style.fill).toBe('rgb(217, 119, 87)');
    expect(bars[3].querySelector('title')?.textContent).toBe('S4 · Live Trader: -$20.00');
    // One slot per trade across the whole chart: however many trades, the newest is never cut off.
    expect(document.querySelector('svg.reports-v2-curve')?.getAttribute('viewBox')).toBe('0 0 4 100');
    const last = bars[bars.length - 1];
    expect(Number(last.getAttribute('x')) + Number(last.getAttribute('width'))).toBeLessThanOrEqual(4);
  });

  it('asks for each pick by its owner, and one earlier bot alone', async () => {
    const fetch = stubFetch();
    render(<ReportsTab venue="paper" view={{ book: 'earlier_bots', bot: 'live_trader' }} />);
    await settle();
    expect(String(fetch.mock.calls[0][0])).toContain('venue=paper&owner=earlier_bots&bot=live_trader');
    cleanup();
    fetch.mockClear();
    render(<ReportsTab venue="paper" view={{ book: 'brain', bot: null }} />);
    await settle();
    expect(String(fetch.mock.calls[0][0])).toContain('venue=paper&owner=brain');
    expect(String(fetch.mock.calls[0][0])).not.toContain('bot=');
  });
});

describe('MonthDetail on Paper', () => {
  const day = (date: string, pnl: number, n: number, byOwner: ReturnType<typeof books>) =>
    ({ date, pnl, trade_count: n, result: pnl > 0 ? 'win' : pnl < 0 ? 'loss' : 'flat', by_owner: byOwner }) as const;
  const MONTH = {
    year: 2026, month: 11, timezone: 'America/New_York', includes_mock_data: false,
    pnl: 5.97, trade_count: 4, winning_days: 1, losing_days: 0, flat_days: 0,
    by_owner: books([23, 1], [-17.03, 3]),
    days: [day('2026-11-12', 5.97, 4, books([23, 1], [-17.03, 3]))],
    weeks: [
      { week_index: 1, pnl: 5.97, trade_count: 4, days: ['2026-11-08', '2026-11-12'], by_owner: books([23, 1], [-17.03, 3]) },
      { week_index: 2, pnl: 0, trade_count: 0, days: ['2026-11-15'], by_owner: books([0, 0]) },
    ],
  } as unknown as MonthCalendarResponse;

  it("lists only the day's traders in its cell, and all four on the month line and the week column", () => {
    render(<MonthDetail data={MONTH} onClose={() => {}} />);
    const splits = screen.getAllByTestId('reports-split');
    const [monthLine, dayCell, weekColumn] = splits;
    expect(partsOf(monthLine)).toEqual(['you', 'claude', 'brain', 'earlier_bots']);
    expect(partsOf(dayCell)).toEqual(['you', 'claude']);
    expect(within(dayCell).getByTestId('reports-split-claude').textContent).toContain('-$17.03');
    expect(partsOf(weekColumn)).toEqual(['you', 'claude', 'brain', 'earlier_bots']);
    // A day and a week with no trade show their total alone.
    expect(splits).toHaveLength(3);
    expect((within(dayCell).getByTestId('reports-split-you').querySelector('i') as HTMLElement).style.background)
      .toBe('rgb(100, 210, 255)');                                          // OWNER_COLORS.you
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
