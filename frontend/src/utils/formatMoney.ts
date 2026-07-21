/**
 * Shared dollar formatter for account/position/order tables.
 * Single source of truth for `$` + thousands-separator formatting
 * (was copy-pasted as local `fmt`/`fmtDollar` helpers in 5 files).
 */
export function formatMoney(n: number | null | undefined, decimals = 2): string {
  if (n == null || !Number.isFinite(n)) return '—';
  return `$${n.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })}`;
}
