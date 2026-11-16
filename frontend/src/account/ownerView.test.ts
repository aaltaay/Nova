import { describe, expect, it } from 'vitest';
import type { Owner } from '../constantGroups/owners';
import { threeBooksHistoryFixture, THREE_BOOKS_ACCOUNT } from './accountFixtures';
import type { HistoryFill, PracticeHistory } from './accountHistoryTypes';
import { positionsByOwner, positionsBySymbol } from './accountPositions';
import {
  ALL_VIEW,
  botsOf,
  dayFillCounts,
  daySplits,
  monthSplit,
  shows,
  tradedIn,
  viewBookDay,
  viewHistory,
  whoName,
} from './ownerView';

const part = (owner: Owner, bot: string | null, realized: number, qty = 10) =>
  ({ owner, bot, qty, closes: true, realized, commission: 1, fees: 0 });

function fill(ts: number, parts: ReturnType<typeof part>[], owner: Owner | null = parts[0].owner): HistoryFill {
  return {
    ts, order_id: ts, symbol: 'ABC', side: 'SELL', qty: parts.reduce((s, p) => s + p.qty, 0), price: 11,
    source: owner === 'you' ? 'manual' : 'bot', bot_id: null, commission: parts.length, fees: 0,
    realized: parts.reduce((s, p) => s + p.realized, 0), fill_estimated: true, fill_basis: 'test',
    owner, bot: parts[0].bot, parts,
  };
}

const sums = (realized: number, fills: number) => ({ realized, fills, commissions: fills, fees: 0 });

const history = (): PracticeHistory => ({
  venue: 'paper', account_id: 'NOVA-PAPER', range: '1M', range_start: null, schema_version: 3, starting_cash: 100_000,
  ledger_opened_at: null,
  equity: [{ ts: 2, net_liquidation: 100_052, cash: 100_052, realized: 52, unrealized: 0,
             you_pnl: 98, claude_pnl: 2, brain_pnl: 0, earlier_bots_pnl: -48,
             you_realized: 98, claude_realized: 2, brain_realized: 0, earlier_bots_realized: -48,
             by_bot: { live_trader: -48 }, by_bot_realized: { live_trader: -48 } }],
  fills: [fill(1, [part('you', null, 98)]), fill(2, [part('earlier_bots', 'live_trader', -48)]),
          fill(3, [part('you', null, 5, 4), part('claude', null, 2, 6)], null)],
  by_source: [],
  by_owner: [{ owner: 'you', bot: null, ...sums(103, 2) },
             { owner: 'earlier_bots', bot: 'live_trader', ...sums(-48, 1) },
             { owner: 'claude', bot: null, ...sums(2, 1) }],
  daily: [{ date: '2026-11-03', realized: 57, commissions: 4, fees: 0, fills: 3, archived: false,
            you: sums(103, 2), claude: sums(2, 1), brain: sums(0, 0), earlier_bots: sums(-48, 1),
            by_bot: { live_trader: sums(-48, 1) } }],
  archives: [],
  components: { realized: 57, unrealized: 0, commissions: 4, sec_finra_fees: 0, bot_realized: -46,
                you_realized: 103, claude_realized: 2, brain_realized: 0, earlier_bots_realized: -48 },
  warnings: [],
});

describe('whose trades the Account page shows (ADR 072)', () => {
  it('All passes the history through unchanged', () => {
    const h = history();
    expect(viewHistory(h, ALL_VIEW)).toBe(h);
  });

  it('You keeps your parts of each fill, your days and your running P&L', () => {
    const you = viewHistory(history(), { book: 'you', bot: null })!;
    expect(you.fills.map((f) => [f.ts, f.realized, f.qty])).toEqual([[1, 98, 10], [3, 5, 4]]);
    expect(you.daily.map((d) => [d.date, d.realized, d.fills])).toEqual([['2026-11-03', 103, 2]]);
    expect(you.components.realized).toBe(103);
    expect(you.equity[0]).toMatchObject({ realized: 98, unrealized: 0, net_liquidation: 100_098 });
    expect(you.by_owner?.map((r) => r.owner)).toEqual(['you']);
  });

  it('Claude is a trader with its own pick, not a bot inside Earlier bots', () => {
    const claude = viewHistory(history(), { book: 'claude', bot: null })!;
    expect(claude.fills.map((f) => [f.ts, f.realized, f.qty])).toEqual([[3, 2, 6]]);
    expect(claude.daily[0].realized).toBe(2);
    expect(claude.equity[0]).toMatchObject({ net_liquidation: 100_002 });
  });

  it('The brain with no trades is an empty book, never another book\'s figures', () => {
    const brain = viewHistory(history(), { book: 'brain', bot: null })!;
    expect(brain.fills).toEqual([]);
    expect(brain.daily).toEqual([]);
    expect(brain.components.realized).toBe(0);
  });

  it('Earlier bots holds the retired bots; one bot is that bot alone', () => {
    const earlier = viewHistory(history(), { book: 'earlier_bots', bot: null })!;
    expect(earlier.fills.map((f) => f.realized)).toEqual([-48]);
    const one = viewHistory(history(), { book: 'earlier_bots', bot: 'live_trader' })!;
    expect(one.daily[0].realized).toBe(-48);
    expect(viewHistory(history(), { book: 'earlier_bots', bot: 'bot_api' })!.fills).toEqual([]);
  });

  it('a history with no split (an older ledger) is never narrowed', () => {
    const old = { ...history(), fills: history().fills.map(({ parts: _parts, ...f }) => f) } as PracticeHistory;
    expect(viewHistory(old, { book: 'you', bot: null })).toBe(old);
  });

  it('names and splits read the wire', () => {
    expect([whoName('you', null), whoName('claude', null), whoName('brain', null), whoName('earlier_bots', 'live_trader'),
            whoName(null, null)]).toEqual(['You', 'Claude', 'The brain', 'Live Trader', 'Nova']);
    expect(shows({ book: 'earlier_bots', bot: null }, 'earlier_bots', 'live_trader')).toBe(true);
    expect(shows({ book: 'you', bot: null }, 'claude', null)).toBe(false);
    expect(botsOf(history())).toEqual(['live_trader']);
    const splits = daySplits(history());
    expect(splits?.get('2026-11-03')).toEqual({ you: 103, claude: 2, brain: 0, earlier_bots: -48 });
    expect(monthSplit(splits, '2026-11')).toEqual({ you: 103, claude: 2, brain: 0, earlier_bots: -48 });
    expect(tradedIn(splits?.get('2026-11-03'))).toEqual(['you', 'claude', 'earlier_bots']);
    expect(dayFillCounts(history(), '2026-11-03')).toEqual({ you: 2, claude: 1, brain: 0, earlier_bots: 1 });
  });

  it("reads one book's day from the account's books", () => {
    expect(viewBookDay(THREE_BOOKS_ACCOUNT.books, ALL_VIEW)).toBeNull();
    expect(viewBookDay(THREE_BOOKS_ACCOUNT.books, { book: 'claude', bot: null })?.day_pnl).toBe(63.76);
    expect(viewBookDay(THREE_BOOKS_ACCOUNT.books, { book: 'brain', bot: null })?.fills_today).toBe(0);
  });

  it('the fixture ledger: every book\'s day adds up to the account\'s', () => {
    const h = threeBooksHistoryFixture(Date.parse('2026-09-18T10:00:00-04:00') / 1000);
    const day = daySplits(h)!.get('2026-09-18')!;
    expect(day.you + day.claude + day.brain + day.earlier_bots).toBeCloseTo(h.daily[1].realized, 6);
    const books = THREE_BOOKS_ACCOUNT.books!;
    expect(books.you.day_pnl + books.claude.day_pnl + books.brain.day_pnl + books.earlier_bots.day_pnl)
      .toBeCloseTo(THREE_BOOKS_ACCOUNT.day_pnl, 6);
  });
});

describe('positions by holder (ADR 072)', () => {
  it('a position becomes one row per holder, each at its own cost and its own size', () => {
    const rows = positionsByOwner([{ symbol: 'spcx', qty: 104, avg_cost: 140.96, mark: 141, unrealized: 4,
      by_owner: [{ owner: 'you', bot: null, qty: 100, avg_cost: 141, unrealized_pnl: 0 },
                 { owner: 'earlier_bots', bot: 'live_trader', qty: 4, avg_cost: 140, unrealized_pnl: 4, handed: true }] }]);
    expect(rows.map((r) => [r.symbol, r.owner, r.bot, r.qty, r.avgCost, r.marketValue, r.handed])).toEqual([
      ['SPCX', 'you', null, 100, 141, 14_100, false], ['SPCX', 'earlier_bots', 'live_trader', 4, 140, 564, true],
    ]);
    const [one] = positionsBySymbol(rows);
    expect([one.qty, one.marketValue, one.unrealized, one.owner, one.handed]).toEqual([104, 14_664, 4, undefined, undefined]);
    expect(one.avgCost).toBeCloseTo((100 * 141 + 4 * 140) / 104, 9);   // each holder at its own cost
  });

  it("Claude's handed shares are their own row: nothing sizes from another trader's", () => {
    const rows = positionsByOwner(THREE_BOOKS_ACCOUNT.positions);
    expect(rows.map((r) => [r.owner, r.qty, r.handed])).toEqual([['you', 100, false], ['claude', 51, true]]);
  });
});
