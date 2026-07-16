/** ADR 005 — chart feature slice public types. */

export interface ChartTradeUpdate {
  price: number;
  timestamp: string | null;
  /** When set, live merges must ignore trades for a different symbol. */
  symbol?: string | null;
}
