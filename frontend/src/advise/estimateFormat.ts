import type { AdviseEstimate } from './types';

/** Loud pre-run cost line. Keep ASCII hyphen in copy; middot is a separator. */
export function formatAdviseCostHeadline(estimate: Pick<AdviseEstimate, 'est_usd' | 'est_minutes'>): string {
  return `Estimate: ~$${estimate.est_usd.toFixed(2)} · ~${estimate.est_minutes} min`;
}

export function formatAdviseActualUsd(usd: number | null | undefined): string | null {
  if (usd == null || Number.isNaN(Number(usd))) return null;
  return `$${Number(usd).toFixed(2)}`;
}

export function formatAdviseActualLine(usd: number | null | undefined): string | null {
  const formatted = formatAdviseActualUsd(usd);
  return formatted ? `Actual: ${formatted}` : null;
}

export function formatAdviseTime(ts: number | null | undefined): string {
  if (!ts) return '';
  return new Date(ts * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

export function formatAdviseHistoryOption(row: {
  created_ts: number;
  status: string;
  actual_usd?: number | null;
}): string {
  const when = formatAdviseTime(row.created_ts);
  const usd = formatAdviseActualUsd(row.actual_usd);
  if (usd) return `${when} · ${row.status} · ${usd}`;
  return `${when} · ${row.status}`;
}

export function estimateMatches(
  estimate: AdviseEstimate | null,
  symbol: string,
  depth: number,
): boolean {
  if (!estimate) return false;
  return estimate.symbol === symbol.trim().toUpperCase() && estimate.depth === depth;
}
