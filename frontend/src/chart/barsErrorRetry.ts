/** Pure helpers for chart /bars error-retry scheduling (testable without hooks). */

export function shouldScheduleBarsErrorRetry(opts: {
  storeHasBars: boolean;
  retriesUsed: number;
  maxRetries: number;
  chartActive: boolean;
}): boolean {
  if (opts.storeHasBars) return false;
  if (opts.retriesUsed >= opts.maxRetries) return false;
  if (!opts.chartActive) return false;
  return true;
}
