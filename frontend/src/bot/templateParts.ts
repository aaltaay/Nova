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

/** A fixed amount as the material says it: "20c" under a dollar, "$1.20" from one. */
function cents(n: number): string {
  return n < 1 ? `${Math.round(n * 100)}c` : money(n);
}

/**
 * The template's targets from its menu choice (#845, operator decisions 2026-10-09 and 2026-10-12): "target 1 20c or
 * 1c under a half / whole dollar · target 2 1c under HOD or the next level · half at each". A short's covers mirror
 * it (1c over, the low of day). A key a template saved before the menu reads the menu's default, as the scanner does.
 */
export function targetsLine(v: Values, short = false): string {
  const c = cents(num(v.target_fixed) ?? 0.2);
  const under = short ? '1c over' : '1c under';
  const day = short ? 'LOD' : 'HOD';
  const name = short ? 'cover' : 'target';
  const kind = (k: ParamValue | undefined, first: boolean): string => {
    switch (k ?? (first ? 'round_or_fixed' : 'hod_or_level')) {
      case 'round_or_fixed':
        return `${c} or ${under} a half / whole dollar`;
      case 'hod_or_level':
        return `${under} ${day} or the next level`;
      case 'fixed':
        return c;
      case 'next_level':
        return `${under} the next level`;
      case 'pullback_high':
        return short ? 'the bounce low' : 'the pullback high';
      case 'hod':
        return `${under} ${day}`;
      default:
        return String(k).replace(/_/g, ' ');
    }
  };
  const t1 = `${name} 1 ${kind(v.target1_kind, true)}`;
  if (v.target2_kind === 'none') return `${t1} · everything at ${name} 1`;
  const pct = num(v.target_split_pct) ?? 50;
  const split = pct === 50 ? 'half at each' : `${trim(pct, 1)}% at ${name} 1, the rest at ${name} 2`;
  return `${t1} · ${name} 2 ${kind(v.target2_kind, false)} · ${split}`;
}

/** The stop the template picked when it is not the pattern's own: just past the nearest half / whole dollar. */
export function stopChoice(v: Values, short = false): string | null {
  if (v.stop_kind !== 'round') return null;
  return short ? 'buy stop just over the nearest half / whole dollar when the risk fits'
    : 'stop just under the nearest half / whole dollar when the risk fits';
}

/** The trade's exits: the stop the template picked (when not the pattern's) and its targets. */
export function exitsLine(v: Values, short = false): string {
  return [stopChoice(v, short), targetsLine(v, short)].filter(Boolean).join(' · ');
}

/**
 * Risk band, the exits and the bot's own window: the same on every setup with a scanner.
 * The window is the template's `bot_window` when the API sends it (inside the arming
 * window, ADR 042 G), else its raw values. How many a day is the sleeve's, not the template's.
 */
export function tradeLine(v: Values, target: string, w?: TemplateBotWindow | null): string {
  const start = w?.start ?? v.bot_window_start;
  const end = w?.end ?? v.bot_window_end;
  return `Risk ${money(num(v.min_stop) ?? 0)}–${money(num(v.stop_cap) ?? 0).replace('$', '')} · ${target} · `
    + `bot ${start}–${end}${w?.clipped ? ' (clipped to the arming window)' : ''}`;
}
