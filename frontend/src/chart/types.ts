/** ADR 005 — chart feature slice public types. */

export interface ChartTradeUpdate {
  price: number;
  timestamp: string | null;
  /** When set, live merges must ignore trades for a different symbol. */
  symbol?: string | null;
  /** `snapshot` = a Level 1 last, not a print: never merged into a candle. */
  source?: 'stream' | 'snapshot' | 'sim';
  /**
   * The day's running volume IBKR reported with this update. The forming
   * candle's volume is what it grew by while the bar was open.
   */
  dayVolume?: number | null;
}
