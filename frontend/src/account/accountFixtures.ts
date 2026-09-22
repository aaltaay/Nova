/**
 * Test fixtures: a Paper ledger history as GET /api/practice/history returns
 * it, and the practice account that goes with it. Like the ledger
 * (practice/ledger.py), every realized figure is NET of commissions and fees:
 * a BUY fill's realized is minus its own costs. The numbers reconcile:
 * net realized 87.10 + open 55.00 = Day's 142.10; gross 97.50 - commissions
 * 10.00 - fees 0.40 = net 87.10.
 */
import type { PracticeAccount } from '../practice/practiceTypes';
import { todayPracticeDate } from './accountFigures';
import type { HistoryFill, PracticeHistory } from './accountHistoryTypes';

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
