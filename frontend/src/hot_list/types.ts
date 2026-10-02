/** Today's hot list on the wire (ADR 043): `GET /api/hot-list`. */

export type HotSide = 'you' | 'nova';

export interface HotEntry {
  symbol: string;
  how: 'auto' | 'star';
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
  default: { buy: HotSide; sell: HotSide };
  entries: HotEntry[];
  yesterday: string[];
  error: string | null;
}
