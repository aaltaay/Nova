/**
 * Today's hot list on the wire (ADR 044, amended 2026-10-06): `GET /api/hot-list`. The list is watching
 * only: it never says who trades a stock (that is the stock's own Buy / Sell switch).
 */

/** How a name came onto the list: the operator's ★, or an auto ☆ (the top of the Gainers board). */
export type HotHow = 'auto' | 'star';

export interface HotEntry {
  symbol: string;
  how: HotHow;
  /** Epoch seconds it joined the list. */
  at: number;
  board: string | null;
  rank: number | null;
  change_pct: number | null;
  /** The setup scanners follow it now; null when the scanner could not be read. */
  followed: boolean | null;
  /** Why it is not followed (null while it is): the reserved slots are full, IBKR has no line, ... */
  why_not_followed: string | null;
}

export interface HotListView {
  schema_version: number;
  date: string;
  cap: number;
  /** `rule` is the leaders rule in words; `error` why the auto feed could not read the board. */
  auto: { n: number; start: string; end: string; rule: string | null; error: string | null };
  entries: HotEntry[];
  yesterday: string[];
  error: string | null;
}
