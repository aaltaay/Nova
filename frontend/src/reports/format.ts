/** Shared $ / date formatters for Reports calendar. */

export function fmtPnl(v: number): string {
  const abs = Math.abs(v).toFixed(2);
  if (v > 0) return `$${abs}`;
  if (v < 0) return `-$${abs}`;
  return '$0.00';
}

export function fmtPnlShort(v: number): string {
  const abs = Math.abs(v);
  const body = abs >= 100 ? abs.toFixed(0) : abs.toFixed(2);
  if (v > 0) return `$${body}`;
  if (v < 0) return `-$${body}`;
  return '$0';
}

export const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
] as const;

export const DOW_LABELS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'] as const;

/** Format R-multiple for Reports v2 panels. */
export function fmtRMultiple(r: number | null | undefined): string {
  if (r == null || Number.isNaN(r)) return '—';
  const sign = r > 0 ? '+' : '';
  return `${sign}${r.toFixed(2)}R`;
}

/** Format percentage for tag win-rate display. */
export function fmtPct(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—';
  return `${v.toFixed(1)}%`;
}
