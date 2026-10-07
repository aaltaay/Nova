/**
 * The pieces every setup's rule lines are made of (ADR 029): a template's numbers in the operator's words. Shared by
 * the long setups' lines (`templateFormat.ts`) and the short ones' (`templateFormatShort.ts`). Pure.
 */
import type { ParamValue, TemplateBotWindow } from './templateTypes';

export type Values = Record<string, ParamValue>;

export function num(v: ParamValue | undefined): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

export function trim(n: number, digits = 2): string {
  return n.toFixed(digits).replace(/\.?0+$/, '');
}

/** A share price in a range: "$3", "$10.5". */
function px(n: number): string {
  return `$${trim(n, 2)}`;
}

export function money(n: number): string {
  const digits = Math.abs(n) < 1 && Math.round(n * 1000) % 10 !== 0 ? 3 : 2;
  return `$${n.toFixed(digits)}`;
}

function range(lo: number | null, hi: number | null, fmt: (n: number) => string, noun: string): string | null {
  if (lo != null && hi != null) return `${fmt(lo)}–${fmt(hi).replace('$', '')}`;
  if (lo != null) return `${noun} ≥ ${fmt(lo)}`;
  if (hi != null) return `${noun} ≤ ${fmt(hi)}`;
  return null;
}

/** The stock filter every setup with a scanner reads (the catalogue's _STOCK). */
export function stockLine(v: Values): string {
  const stock = ['HOD Momo names'];
  stock.push(range(num(v.min_price), num(v.max_price), px, 'price') ?? 'any price');
  stock.push(num(v.max_float_m) != null ? `float ≤ ${trim(num(v.max_float_m)!, 1)}M` : 'any float');
  if (num(v.min_change_pct) != null) stock.push(`up ≥ ${trim(num(v.min_change_pct)!)}%`);
  if (num(v.min_rvol) != null) stock.push(`RVOL ≥ ${trim(num(v.min_rvol)!)}x`);
  if (v.require_catalyst) stock.push('a catalyst');
  if (v.min_grade === 'A') stock.push('grade A');
  if (v.min_grade === 'B') stock.push('grade B+');
  return stock.join(' · ');
}

export function bars(lo: number | null, hi: number | null): string {
  const a = lo ?? 1;
  const b = hi ?? a;
  return a === b ? `${a}` : `${a}–${b}`;
}

export function ema(v: Values): string {
  const tol = num(v.ema_tol) ? ` (−${trim(num(v.ema_tol)!)}%)` : '';
  return `${num(v.ema_period)} EMA${tol}`;
}

/**
 * Risk band, target 1 and the bot's own window: the same on every setup with a scanner.
 * The window is the template's `bot_window` when the API sends it (inside the arming
 * window, ADR 042 G), else its raw values. How many a day is the sleeve's, not the template's.
 */
export function tradeLine(v: Values, target: string, w?: TemplateBotWindow | null): string {
  const start = w?.start ?? v.bot_window_start;
  const end = w?.end ?? v.bot_window_end;
  return `Risk ${money(num(v.min_stop) ?? 0)}–${money(num(v.stop_cap) ?? 0).replace('$', '')} · ${target} · `
    + `bot ${start}–${end}${w?.clipped ? ' (clipped to the arming window)' : ''}`;
}
