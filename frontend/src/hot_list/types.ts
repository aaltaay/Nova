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
  /** The setup scanners follow it now. */
  followed: boolean | null;
}

export interface HotListView {
  schema_version: number;
  date: string;
  cap: number;
  auto: { n: number; start: string; end: string; rule: Record<string, unknown> | null; error: string | null };
  default: { buy: HotSide; sell: HotSide };
  entries: HotEntry[];
  yesterday: string[];
  error: string | null;
}
