/** Pure money / P&L helpers for the GlobalAppBar cluster. */
import { GLOBAL_BAR_OFFLINE_PLACEHOLDER } from '../constants';
import { PNL_TONE_MIN_USD } from '../constantGroups/account_page';
import { formatMoney } from '../utils/formatMoney';

export function dayPnlFromSummary(
  realized: number | null | undefined,
  unrealized: number | null | undefined,
): number | null {
  const hasRealized = realized != null && Number.isFinite(realized);
  const hasUnrealized = unrealized != null && Number.isFinite(unrealized);
  if (!hasRealized && !hasUnrealized) return null;
  return (hasRealized ? (realized as number) : 0) + (hasUnrealized ? (unrealized as number) : 0);
}

/** True when `n` shows as zero at `decimals` places (so it carries no sign). */
function roundsToZero(n: number, decimals: number): boolean {
  return Number(Math.abs(n).toFixed(decimals)) === 0;
}

/** Signed `$` string for P&L (`+$1.00` / `-$1.00` / `$0.00` / `--`); never `-$0.00`. */
export function formatSignedMoney(n: number | null | undefined, decimals = 2): string {
  if (n == null || !Number.isFinite(n)) return GLOBAL_BAR_OFFLINE_PLACEHOLDER;
  if (roundsToZero(n, decimals)) return formatMoney(0, decimals);
  const body = formatMoney(Math.abs(n), decimals);
  if (n > 0) return `+${body}`;
  if (n < 0) return `-${body}`;
  return body;
}

/** Signed percent for Day's (`+0.12%` / `-0.12%` / `0.00%` / `--`); never `-0.00%`. */
export function formatSignedPercent(n: number | null | undefined, decimals = 2): string {
  if (n == null || !Number.isFinite(n)) return GLOBAL_BAR_OFFLINE_PLACEHOLDER;
  if (roundsToZero(n, decimals)) return `${(0).toFixed(decimals)}%`;
  const body = `${Math.abs(n).toFixed(decimals)}%`;
  if (n > 0) return `+${body}`;
  if (n < 0) return `-${body}`;
  return body;
}

/** Red / green only once P&L moves PNL_TONE_MIN_USD either way (operator ask, 2026-09-22). */
export function pnlToneClass(n: number | null | undefined, minAbs: number = PNL_TONE_MIN_USD): string {
  if (n == null || !Number.isFinite(n) || Math.abs(n) < minAbs || roundsToZero(n, 2)) {
    return 'global-app-bar__tone--flat';
  }
  return n > 0 ? 'global-app-bar__tone--up' : 'global-app-bar__tone--down';
}
