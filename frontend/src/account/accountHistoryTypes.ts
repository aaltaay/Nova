/**
 * Wire shape of GET /api/practice/history (AGENTS.md section 3, "The ledger
 * as history"). A pure derivation of the ledger events: nothing here is a live
 * mark, and nothing is drawn between events.
 */
import type { AccountRange } from '../constantGroups/account_page';
import type { PracticeVenue } from '../constantGroups/practice';
import type { Owner } from '../constantGroups/owners';

/** One point after every `filled` and `rollover` event, in event order. */
export interface EquityPoint {
  ts: number;
  net_liquidation: number;
  cash: number;
  realized: number;
  unrealized: number;
  /** ADR 072: each book's running P&L since the ledger opened, at the event's marks, and its realized part. */
  you_pnl?: number;
  claude_pnl?: number;
  brain_pnl?: number;
  earlier_bots_pnl?: number;
  by_bot?: Record<string, number>;
  you_realized?: number;
  claude_realized?: number;
  brain_realized?: number;
  earlier_bots_realized?: number;
  by_bot_realized?: Record<string, number>;
}

/** Whose book (ADR 072): `you` | `claude` | `brain` | `earlier_bots`; null for one of Nova's own closes. */
export type HistoryOwner = Owner;

/** How one fill split across its holders, each at its own cost (ADR 069). */
export interface HistoryFillPart {
  owner: HistoryOwner;
  /** The retired bot inside Earlier bots (the order's origin); null for every other book. */
  bot: string | null;
  qty: number;
  closes: boolean;
  realized: number;
  commission: number;
  fees: number;
  /** `you`: you closed these shares after their trader handed them to you; booked on its record (ADR 072). */
  closed_by?: 'you' | null;
}

/** One book's (or one bot's) sums over a day or a range. */
export interface HistoryBookSums {
  realized: number;
  fills: number;
  commissions: number;
  fees: number;
}

export interface HistoryByOwner extends HistoryBookSums {
  owner: HistoryOwner;
  bot: string | null;
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
  /** ADR 072: whose order it was, and how it split across the holders. */
  owner?: HistoryOwner | null;
  bot?: string | null;
  parts?: HistoryFillPart[];
  /** `you` when any part closed shares handed to you. */
  closed_by?: 'you' | null;
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
  /** ADR 072: each book's day, and each retired bot's. */
  you?: HistoryBookSums;
  claude?: HistoryBookSums;
  brain?: HistoryBookSums;
  earlier_bots?: HistoryBookSums;
  by_bot?: Record<string, HistoryBookSums>;
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
  /** ADR 072: each book's realized, at its own cost (`bot_realized` is every book's but yours). */
  you_realized?: number;
  claude_realized?: number;
  brain_realized?: number;
  earlier_bots_realized?: number;
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
  /** ADR 072: each holder, first-fill order. */
  by_owner?: HistoryByOwner[];
  daily: HistoryDaily[];
  archives: HistoryArchive[];
  components: HistoryComponents;
  warnings: string[];
}
