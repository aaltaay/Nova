/** Pure helpers for chart /bars error-retry scheduling (testable without hooks). */

export function shouldScheduleBarsErrorRetry(opts: {
  background: boolean;
  storeHasBars: boolean;
  retryAlreadyUsed: boolean;
  chartActive: boolean;
}): boolean {
  if (opts.background) return false;
  if (opts.storeHasBars) return false;
  if (opts.retryAlreadyUsed) return false;
  if (!opts.chartActive) return false;
  return true;
}
