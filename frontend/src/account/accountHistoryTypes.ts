/**
 * Wire shape of GET /api/practice/history (AGENTS.md section 3, "The ledger
 * as history"). A pure derivation of the ledger events: nothing here is a live
 * mark, and nothing is drawn between events.
 */
import type { AccountRange } from '../constantGroups/account_page';
import type { PracticeVenue } from '../constantGroups/practice';

/** One point after every `filled` and `rollover` event, in event order. */
export interface EquityPoint {
  ts: number;
  net_liquidation: number;
  cash: number;
  realized: number;
  unrealized: number;
}

export interface HistoryFill {
  ts: number;
  order_id: number;
  symbol: string;
  side: 'BUY' | 'SELL';
  qty: number;
  price: number;
  /** ADR 007 source stamp (manual / bot / auto_paper / ...); null on a legacy row. */
  source: string | null;
  bot_id: string | null;
  commission: number;
  /** SEC + FINRA pass-through on this fill. */
  fees: number;
  /** This fill's own realized contribution on the ledger's cost basis. */
  realized: number;
  fill_estimated: true;
  fill_basis: string | null;
}

export interface HistoryBySource {
  source: string | null;
  bot_id: string | null;
  realized: number;
  fills: number;
  commissions: number;
  fees: number;
}

export interface HistoryDaily {
  /** Practice day (04:00 ET rollover) as its ET calendar date, YYYY-MM-DD. */
  date: string;
  realized: number;
  commissions: number;
  fees: number;
  fills: number;
  /** True for a day that belongs to an archived Paper ledger. */
  archived: boolean;
}

export interface HistoryArchive {
  file: string;
  opened_at: string | null;
  closed_at: string | null;
  realized: number;
  days: number;
}

export interface HistoryComponents {
  realized: number;
  unrealized: number;
  commissions: number;
  sec_finra_fees: number;
  bot_realized: number;
}

export interface PracticeHistory {
  venue: PracticeVenue;
  account_id: string | null;
  range: AccountRange;
  /** Epoch seconds of the first practice day the range covers; null for ALL. */
  range_start: number | null;
  schema_version: number;
  starting_cash: number;
  /** ISO ET timestamp the ledger opened. */
  ledger_opened_at: string | null;
  equity: EquityPoint[];
  fills: HistoryFill[];
  by_source: HistoryBySource[];
  daily: HistoryDaily[];
  archives: HistoryArchive[];
  components: HistoryComponents;
  warnings: string[];
}
