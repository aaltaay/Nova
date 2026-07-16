/** Whether empty REST bars may fall back to synthetic mock candles. */

export function allowMockBarsFallback(discoveryProvider: string): boolean {
  // Under IBKR discovery, mock bars would look like an IBKR quote — forbidden.
  return discoveryProvider !== 'ibkr';
}

export function emptyBarsMessage(discoveryProvider: string): string {
  if (discoveryProvider === 'ibkr') {
    return 'No IBKR historical bars available for this symbol/timeframe.';
  }
  return 'No chart bars available.';
}
