/**
 * Maps each ticker / scanner surface to its live data provider.
 * Product lock: scanner + quote/chart are IBKR; Alpaca is listing/news aux only.
 */

export type DataSourceRow = {
  /** What the user is looking at (scanner, quote, L2, …). */
  role: string;
  /** Human-readable provider name. */
  source: string;
  /** Optional short note (e.g. IEX vs SIP tier). */
  detail?: string;
};

export type DataSourceInputs = {
  /** Scanner discovery provider — product path is always 'ibkr'. */
  discoveryProvider: string;
  /** Alpaca market-data tier used for aux (news/listing), not live scanner. */
  alpacaFeed: string;
  /** Whether IB Gateway is connected (gates Level 2). */
  ibkrConnected: boolean;
};

/**
 * Build the attribution rows shown on the ticker side panel.
 * Order is intentional: scanner → quote/chart → L2 → listing → fundamentals.
 */
export function buildTickerDataSources(input: DataSourceInputs): DataSourceRow[] {
  const { ibkrConnected } = input;

  return [
    {
      role: 'Scanner rows',
      source: 'Interactive Brokers',
      detail: 'Live Gateway market scanner (IBKR only)',
    },
    {
      role: 'Quote & chart',
      source: 'Interactive Brokers',
      detail: 'IBKR only — historical bars + live last-price (no Alpaca fallback)',
    },
    {
      role: 'Level 2',
      source: ibkrConnected ? 'Interactive Brokers' : 'IBKR (offline)',
      detail: ibkrConnected
        ? 'Smart Depth / TotalView via Gateway'
        : 'Connect IB Gateway to stream depth',
    },
    {
      role: 'Time & Sales',
      source: ibkrConnected ? 'Interactive Brokers' : 'IBKR (offline)',
      detail: ibkrConnected
        ? 'reqTickByTickData AllLast — every print, IBKR only'
        : 'Connect IB Gateway to stream Time & Sales',
    },
    {
      role: 'Listing flags',
      source: 'Alpaca Assets API',
      detail: 'Tradable / shortable / margin metadata only — not prices or depth',
    },
    {
      role: 'Fundamentals',
      source: 'Yahoo Finance',
      detail: 'Float, short interest, sector, 52-week range',
    },
  ];
}
