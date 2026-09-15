import type { AdviseEstimate } from './types';

/** Loud pre-run cost line. Keep ASCII hyphen in copy; middot is a separator. */
export function formatAdviseCostHeadline(estimate: Pick<AdviseEstimate, 'est_usd' | 'est_minutes'>): string {
  return `~$${estimate.est_usd.toFixed(2)} · ~${estimate.est_minutes} min`;
}

export function estimateMatches(
  estimate: AdviseEstimate | null,
  symbol: string,
  depth: number,
): boolean {
  if (!estimate) return false;
  return estimate.symbol === symbol.trim().toUpperCase() && estimate.depth === depth;
}
