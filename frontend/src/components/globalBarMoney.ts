/** Pure money / P&L helpers for the GlobalAppBar cluster. */
import { GLOBAL_BAR_OFFLINE_PLACEHOLDER } from '../constants';
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

/** Signed `$` string for P&L (`+$1.00` / `-$1.00` / `$0.00` / `--`). */
export function formatSignedMoney(n: number | null | undefined, decimals = 2): string {
  if (n == null || !Number.isFinite(n)) return GLOBAL_BAR_OFFLINE_PLACEHOLDER;
  const body = formatMoney(Math.abs(n), decimals);
  if (n > 0) return `+${body}`;
  if (n < 0) return `-${body}`;
  return body;
}

export function pnlToneClass(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n) || n === 0) return 'global-app-bar__tone--flat';
  return n > 0 ? 'global-app-bar__tone--up' : 'global-app-bar__tone--down';
}
