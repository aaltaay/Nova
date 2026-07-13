/** Shared row shape for the Gappers / Movers / After Hours scanner tables. */
export interface ScannerRow {
  symbol: string;
  price: number;
  prev_close: number;
  change_pct: number;
  change_abs: number;
  gap_percent: number | null;
  volume: number;
  rel_volume: number | null;
  has_news: boolean;
  newest_headline_at: string | null;
  market_cap: number | null;
  float: number | null;
  short_interest: number | null;
  short_ratio: number | null;
}

// Legacy aliases — kept for any remaining narrower references
export type Gapper = ScannerRow;
export type Mover = ScannerRow;
export type Afterhours = ScannerRow;

export type SortDir = 'asc' | 'desc' | null;
export interface SortConfig { key: string; dir: SortDir; }
