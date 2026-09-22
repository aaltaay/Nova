/**
 * Shared dollar formatter for account/position/order tables.
 * Single source of truth for `$` + thousands-separator formatting
 * (was copy-pasted as local `fmt`/`fmtDollar` helpers in 5 files).
 */
export function formatMoney(n: number | null | undefined, decimals = 2): string {
  if (n == null || !Number.isFinite(n)) return '—';
  // A figure that rounds to zero is zero: never "$-0.00" (a -0 commission read that way).
  const value = Number(Math.abs(n).toFixed(decimals)) === 0 ? 0 : n;
  return `$${value.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })}`;
}
