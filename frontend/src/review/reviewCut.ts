/** Drop bars the as-of time has not closed yet. Same rule as tools/nova_review_causal.py. */

import type { RawBar } from '../tickerChartData';
import type { ReviewTf } from './reviewQuery';

const STEP_MS: Record<Exclude<ReviewTf, '1d'>, number> = {
  '1m': 60_000,
  '5m': 300_000,
  '10s': 10_000,
};

export function cutBars(bars: RawBar[], tf: ReviewTf, asOfIso: string): RawBar[] {
  if (tf === '1d') {
    const day = asOfIso.slice(0, 10);
    return bars.filter((bar) => bar.t.slice(0, 10) <= day);
  }
  const asOf = Date.parse(asOfIso);
  const step = STEP_MS[tf];
  if (!Number.isFinite(asOf)) return [];
  return bars.filter((bar) => {
    const start = Date.parse(bar.t);
    return Number.isFinite(start) && start + step <= asOf;
  });
}
