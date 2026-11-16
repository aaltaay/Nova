/**
 * Test fixtures: a Paper ledger history as GET /api/practice/history returns
 * it, and the practice account that goes with it. Like the ledger
 * (practice/ledger.py), every realized figure is NET of commissions and fees:
 * a BUY fill's realized is minus its own costs. The numbers reconcile:
 * net realized 87.10 + open 55.00 = Day's 142.10; gross 97.50 - commissions
 * 10.00 - fees 0.40 = net 87.10.
 */
import type { Owner } from '../constantGroups/owners';
import type { PracticeAccount } from '../practice';
import { todayPracticeDate } from './accountFigures';
import type { HistoryBookSums, HistoryFill, PracticeHistory } from './accountHistoryTypes';

const ARCHIVE_FILE = 'practice-paper-2026-09-18T1612.json';

export function paperHistoryFixture(nowTs: number = Math.floor(Date.now() / 1000)): PracticeHistory {
  const today = todayPracticeDate(new Date(nowTs * 1000));
  const at = (minutesAgo: number): number => nowTs - minutesAgo * 60;
  const fill = (
    minutesAgo: number,
    order_id: number,
    symbol: string,
    side: 'BUY' | 'SELL',
    qty: number,
    price: number,
    source: string,
    bot_id: string | null,
    commission: number,
    fees: number,
    realized: number,
  ): HistoryFill => ({
    ts: at(minutesAgo), order_id, symbol, side, qty, price, source, bot_id,
    commission, fees, realized, fill_estimated: true, fill_basis: 'quote',
  });
  // realized = gross price P&L - this fill's commission - its fees (net).
  const fills: HistoryFill[] = [
    fill(60, 1, 'GRML', 'BUY', 500, 5.1, 'manual', null, 2.5, 0, -2.5),
    fill(57, 2, 'GRML', 'SELL', 500, 5.35, 'manual', null, 2.5, 0.2, 122.3),
    fill(46, 3, 'QNME', 'BUY', 250, 14.21, 'bot', 'momo-1', 1.25, 0, -1.25),
    fill(38, 4, 'QNME', 'SELL', 250, 14.1, 'bot', 'momo-1', 1.25, 0.2, -28.95),
    fill(9, 5, 'GRML', 'BUY', 300, 8.75, 'manual', null, 1.5, 0, -1.5),
    fill(3, 6, 'GRML', 'BUY', 100, 8.8, 'manual', null, 1.0, 0, -1.0),
  ];
  const cashAfter = [97447.5, 100119.8, 96566.05, 100089.6, 97463.1, 96582.1];
  const equity = [
    { ts: at(600), net_liquidation: 100000, cash: 100000, realized: 0, unrealized: 0 },
    ...fills.map((f, i) => ({
      ts: f.ts,
      net_liquidation: 100000 + fills.slice(0, i + 1).reduce((s, x) => s + x.realized, 0),
      cash: cashAfter[i],
      realized: fills.slice(0, i + 1).reduce((s, x) => s + x.realized, 0),
      unrealized: 0,
    })),
  ];
  return {
    venue: 'paper',
    account_id: 'NOVA-PAPER',
    range: 'ALL',
    range_start: null,
    schema_version: 1,
    starting_cash: 100000,
    ledger_opened_at: '2026-09-18T16:12:40-04:00',
    equity,
    fills,
    by_source: [
      { source: 'manual', bot_id: null, realized: 117.3, fills: 4, commissions: 7.5, fees: 0.2 },
      { source: 'bot', bot_id: 'momo-1', realized: -30.2, fills: 2, commissions: 2.5, fees: 0.2 },
    ],
    daily: [
      { date: '2026-09-10', realized: 96.35, commissions: 2, fees: 0.2, fills: 2, archived: true },
      { date: today, realized: 87.1, commissions: 10, fees: 0.4, fills: 6, archived: false },
    ],
    archives: [
      { file: ARCHIVE_FILE, opened_at: '2026-09-04T09:30:00-04:00', closed_at: '2026-09-18T16:12:40-04:00', realized: 192.85, days: 10 },
    ],
    components: { realized: 87.1, unrealized: 55, commissions: 10, sec_finra_fees: 0.4, bot_realized: -30.2 },
    warnings: [],
  };
}

export const PAPER_ACCOUNT_TODAY: PracticeAccount = {
  venue: 'paper',
  account_id: 'NOVA-PAPER',
  starting_cash: 100000,
  cash: 96582.1,
  buying_power: 386328.4,
  net_liquidation: 100142.1,
  gross_position_value: 3560,
  realized_pnl: 87.1,
  realized_today: 87.1,
  unrealized_pnl: 55,
  day_pnl: 142.1,
  day_started_et: '2026-09-21T04:00:00-04:00',
  commissions_today: 10.4,
  positions: [{ symbol: 'GRML', qty: 400, avg_cost: 8.7625, mark: 8.9, unrealized: 55 }],
  working: [],
  fills_today: 6,
  schema_version: 1,
  updated_at: '2026-09-21T17:42:03-04:00',
};

/* ------------------------------------------------------------------ three books (ADR 072) */

const sums = (realized: number, fills: number, commissions: number, fees: number): HistoryBookSums =>
  ({ realized, fills, commissions, fees });
const NONE = sums(0, 0, 0, 0);

/**
 * A Paper ledger history at schema 3 (ADR 072): today you traded FCUV, Claude traded LFTO and VTSI -- and you
 * closed Claude's VTSI after Claude handed it to you, so that part stays Claude's, "closed by you" -- and two
 * days ago a retired bot (the Live Trader) traded QNME. The brain never traded. Every part reconciles to its
 * fill and every book's day to the account's: today you +1.98, Claude +65.80 = +67.78.
 */
export function threeBooksHistoryFixture(nowTs: number = Math.floor(Date.now() / 1000)): PracticeHistory {
  const today = todayPracticeDate(new Date(nowTs * 1000));
  const before = todayPracticeDate(new Date((nowTs - 2 * 86_400) * 1000));
  const at = (minutesAgo: number): number => nowTs - minutesAgo * 60;
  const fill = (
    minutesAgo: number, order_id: number, symbol: string, side: 'BUY' | 'SELL', qty: number, price: number,
    owner: Owner, bot: string | null, commission: number, fees: number, realized: number,
    closedBy: 'you' | null = null,
  ): HistoryFill => ({
    ts: at(minutesAgo), order_id, symbol, side, qty, price, source: owner === 'you' ? 'manual' : 'bot',
    bot_id: null, commission, fees, realized, fill_estimated: true, fill_basis: 'quote',
    owner: closedBy ? 'you' : owner, bot,
    parts: [{ owner, bot, qty, closes: side === 'SELL', realized, commission, fees, closed_by: closedBy }],
    closed_by: closedBy,
  });
  const fills: HistoryFill[] = [
    fill(2 * 24 * 60 + 40, 1, 'QNME', 'BUY', 50, 14, 'earlier_bots', 'live_trader', 0.5, 0, -0.5),
    fill(2 * 24 * 60 + 30, 2, 'QNME', 'SELL', 50, 14.2, 'earlier_bots', 'live_trader', 0.5, 0.01, 9.49),
    fill(60, 3, 'FCUV', 'BUY', 100, 5.17, 'you', null, 1, 0, -1),
    fill(58, 4, 'FCUV', 'SELL', 100, 5.21, 'you', null, 1, 0.02, 2.98),
    fill(40, 5, 'LFTO', 'BUY', 420, 23.81, 'claude', null, 2.1, 0, -2.1),
    fill(38, 6, 'LFTO', 'SELL', 420, 24.05, 'claude', null, 2.1, 0.3, 98.4),
    fill(20, 7, 'VTSI', 'BUY', 1000, 3.72, 'claude', null, 5, 0, -5),
    fill(10, 8, 'VTSI', 'SELL', 1000, 3.7, 'claude', null, 5, 0.5, -25.5, 'you'),
  ];
  const running: Record<Owner, number> = { you: 0, claude: 0, brain: 0, earlier_bots: 0 };
  let realized = 0;
  const equity = [
    { ts: at(3 * 24 * 60), net_liquidation: 100000, cash: 100000, realized: 0, unrealized: 0,
      you_pnl: 0, claude_pnl: 0, brain_pnl: 0, earlier_bots_pnl: 0, you_realized: 0, claude_realized: 0,
      brain_realized: 0, earlier_bots_realized: 0, by_bot: { live_trader: 0 }, by_bot_realized: { live_trader: 0 } },
    ...fills.map((f) => {
      const owner = f.parts![0].owner;
      running[owner] += f.realized;
      realized += f.realized;
      return {
        ts: f.ts, net_liquidation: 100000 + realized, cash: 100000 + realized, realized, unrealized: 0,
        you_pnl: running.you, claude_pnl: running.claude, brain_pnl: 0, earlier_bots_pnl: running.earlier_bots,
        you_realized: running.you, claude_realized: running.claude, brain_realized: 0,
        earlier_bots_realized: running.earlier_bots,
        by_bot: { live_trader: running.earlier_bots }, by_bot_realized: { live_trader: running.earlier_bots },
      };
    }),
  ];
  const liveTrader = sums(8.99, 2, 1, 0.01);
  return {
    venue: 'paper', account_id: 'NOVA-PAPER', range: 'ALL', range_start: null, schema_version: 3,
    starting_cash: 100000, ledger_opened_at: '2026-09-01T09:00:00-04:00',
    equity, fills, by_source: [],
    by_owner: [
      { owner: 'earlier_bots', bot: 'live_trader', ...liveTrader },
      { owner: 'you', bot: null, ...sums(1.98, 2, 2, 0.02) },
      { owner: 'claude', bot: null, ...sums(65.8, 4, 14.2, 0.8) },
    ],
    daily: [
      { date: before, realized: 8.99, commissions: 1, fees: 0.01, fills: 2, archived: false,
        you: NONE, claude: NONE, brain: NONE, earlier_bots: liveTrader, by_bot: { live_trader: liveTrader } },
      { date: today, realized: 67.78, commissions: 16.2, fees: 0.82, fills: 6, archived: false,
        you: sums(1.98, 2, 2, 0.02), claude: sums(65.8, 4, 14.2, 0.8), brain: NONE, earlier_bots: NONE, by_bot: {} },
    ],
    archives: [],
    components: {
      realized: 76.77, unrealized: 0, commissions: 17.2, sec_finra_fees: 0.83, bot_realized: 74.79,
      you_realized: 1.98, claude_realized: 65.8, brain_realized: 0, earlier_bots_realized: 8.99,
    },
    warnings: [],
  };
}

const day = (day_pnl: number, realized_today: number, unrealized_pnl: number, fills_today: number, commissions_today: number) =>
  ({ day_pnl, realized_today, unrealized_pnl, fills_today, commissions_today });

/** The account that goes with `threeBooksHistoryFixture`: you hold 100 RUNR, and 51 RUNR Claude handed you. */
export const THREE_BOOKS_ACCOUNT: PracticeAccount = {
  ...PAPER_ACCOUNT_TODAY,
  cash: 98_340,
  net_liquidation: 100_092.73,
  gross_position_value: 1_752.73,
  realized_pnl: 76.77,
  realized_today: 67.78,
  unrealized_pnl: 15.96,
  day_pnl: 83.74,
  commissions_today: 17.02,
  positions: [{
    symbol: 'RUNR', qty: 151, avg_cost: 11.5, mark: 11.61, unrealized: 15.96,
    by_owner: [
      { owner: 'you', bot: null, qty: 100, avg_cost: 11.43, unrealized_pnl: 18, handed: false },
      { owner: 'claude', bot: null, qty: 51, avg_cost: 11.65, unrealized_pnl: -2.04, handed: true },
    ],
  }],
  fills_today: 6,
  schema_version: 3,
  books: {
    you: day(19.98, 1.98, 18, 2, 2.02),
    claude: { ...day(63.76, 65.8, -2.04, 4, 15), budget_usd: 25_000, budget_used_usd: 592.11 },
    brain: { ...day(0, 0, 0, 0, 0), budget_usd: 25_000, budget_used_usd: 0 },
    earlier_bots: { ...day(0, 0, 0, 0, 0), by_bot: {} },
  },
};
