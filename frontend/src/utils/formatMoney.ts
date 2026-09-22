/**
 * Shared dollar formatter for account/position/order tables.
 * Single source of truth for `$` + thousands-separator formatting
 * (was copy-pasted as local `fmt`/`fmtDollar` helpers in 5 files).
 */
export function formatMoney(n: number | null | undefined, decimals = 2): string {
  if (n == null || !Number.isFinite(n)) return '—';
  // A figure that rounds to zero is zero: never "$-0.00" (a -0 commission read that way).
  const value = Number(Math.abs(n).toFixed(decimals)) === 0 ? 0 : n;
  const body = Math.abs(value).toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  // The sign leads the dollar sign: "-$5.00", as the header writes it, never
  // "$-5.00" (QA W20 / D18, 2026-09-22).
  return value < 0 ? `-$${body}` : `$${body}`;
}
