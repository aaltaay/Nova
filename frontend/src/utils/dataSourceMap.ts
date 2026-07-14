/**
 * Maps each ticker / scanner surface to its live data provider.
 * Kept pure so Settings feed switches stay honest in the UI and in tests.
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
  /** Scanner discovery provider: 'alpaca' | 'ibkr'. */
  discoveryProvider: string;
  /** Alpaca market-data tier used for bars / Alpaca snapshots: 'iex' | 'sip'. */
  alpacaFeed: string;
  /** Whether IB Gateway is connected (gates Level 2). */
  ibkrConnected: boolean;
};

function alpacaFeedLabel(alpacaFeed: string): string {
  const tier = alpacaFeed.toUpperCase();
  return `Alpaca ${tier}`;
}

/**
 * Build the attribution rows shown on the ticker side panel.
 * Order is intentional: scanner → quote/chart → L2 → listing → fundamentals.
 */
export function buildTickerDataSources(input: DataSourceInputs): DataSourceRow[] {
  const { discoveryProvider, alpacaFeed, ibkrConnected } = input;
  const scannerIsIbkr = discoveryProvider === 'ibkr';
  const alpaca = alpacaFeedLabel(alpacaFeed);

  return [
    {
      role: 'Scanner rows',
      source: scannerIsIbkr ? 'Interactive Brokers' : 'Alpaca',
      detail: scannerIsIbkr
        ? 'Live Gateway scan (Settings → discovery)'
        : `${alpaca} screener (Settings → discovery)`,
    },
    {
      role: 'Quote & chart',
      source: scannerIsIbkr ? 'IBKR + Alpaca' : alpaca,
      detail: scannerIsIbkr
        ? 'Price prefers IBKR cache; bars/chart still Alpaca'
        : 'Alpaca snapshot + historical bars',
    },
    {
      role: 'Level 2',
      source: ibkrConnected ? 'Interactive Brokers' : 'IBKR (offline)',
      detail: ibkrConnected
        ? 'Smart Depth / TotalView via Gateway'
        : 'Connect IB Gateway to stream depth',
    },
    {
      role: 'Broker listing',
      source: 'Alpaca Assets API',
      detail: 'Tradable / shortable / margin flags only — not prices',
    },
    {
      role: 'Fundamentals',
      source: 'Yahoo Finance',
      detail: 'Float, short interest, sector, 52-week range',
    },
  ];
}
