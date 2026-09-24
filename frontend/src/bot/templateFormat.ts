/**
 * A template's numbers in words (ADR 029): the setup card's rule lines and the
 * editor's values are built from the parameters the scanner runs on, never
 * written by hand, so the card cannot say a rule the scanner does not keep.
 * Pure.
 */
import type { ParamSpec, ParamValue, SetupTemplate } from './templateTypes';

type Values = Record<string, ParamValue>;

function num(v: ParamValue | undefined): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

function trim(n: number, digits = 2): string {
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

/** One value as the operator reads it: "$0.20", "5%", "10 bars", "07:00 ET", "off". */
export function formatValue(spec: ParamSpec, value: ParamValue | undefined): string {
  if (value === null || value === undefined) return spec.nullable ? 'off' : '—';
  if (spec.kind === 'bool') return value ? 'on' : 'off';
  if (spec.kind === 'time') return `${value} ET`;
  if (spec.kind === 'choice') return spec.choices.find(c => c.value === value)?.label ?? String(value);
  const n = num(value);
  if (n == null) return String(value);
  if (spec.unit === '$') return money(n);
  if (spec.unit.startsWith('%')) return `${trim(n, 2)}${spec.unit}`;
  if (spec.unit === 'x' || spec.unit === 'R') return `${trim(n, 2)}${spec.unit}`;
  if (spec.unit.startsWith('M shares')) return `${trim(n, 1)}M`;
  if (spec.unit === 'shares') return `${Math.round(n).toLocaleString('en-US')} shares`;
  return spec.unit ? `${trim(n, 3)} ${spec.unit}` : trim(n, 3);
}

/** The typed text of an input -> a value, or the reason it is refused (the backend checks again). */
export function parseInput(spec: ParamSpec, raw: string): { value: ParamValue } | { error: string } {
  const text = raw.trim();
  if (text === '' && spec.nullable) return { value: null };
  if (spec.kind === 'time') {
    return /^([01]\d|2[0-3]):[0-5]\d$/.test(text) ? { value: text } : { error: 'a time like 07:00' };
  }
  const n = Number(text);
  if (text === '' || !Number.isFinite(n)) return { error: 'a number' };
  if (spec.kind === 'int' && !Number.isInteger(n)) return { error: 'a whole number' };
  if (typeof spec.min === 'number' && n < spec.min) return { error: `at least ${spec.min}` };
  if (typeof spec.max === 'number' && n > spec.max) return { error: `at most ${spec.max}` };
  return { value: n };
}

export function changedKeys(a: Values, b: Values): string[] {
  return Object.keys({ ...a, ...b }).filter(k => a[k] !== b[k]);
}

function range(lo: number | null, hi: number | null, fmt: (n: number) => string, noun: string): string | null {
  if (lo != null && hi != null) return `${fmt(lo)}–${fmt(hi).replace('$', '')}`;
  if (lo != null) return `${noun} ≥ ${fmt(lo)}`;
  if (hi != null) return `${noun} ≤ ${fmt(hi)}`;
  return null;
}

function firstPullbackLines(v: Values): [string, string][] {
  const stock = ['HOD Momo names'];
  stock.push(range(num(v.min_price), num(v.max_price), px, 'price') ?? 'any price');
  stock.push(num(v.max_float_m) != null ? `float ≤ ${trim(num(v.max_float_m)!, 1)}M` : 'any float');
  if (num(v.min_change_pct) != null) stock.push(`up ≥ ${trim(num(v.min_change_pct)!)}%`);
  if (num(v.min_rvol) != null) stock.push(`RVOL ≥ ${trim(num(v.min_rvol)!)}x`);
  if (v.require_catalyst) stock.push('a catalyst');
  if (v.min_grade === 'A') stock.push('grade A');
  if (v.min_grade === 'B') stock.push('grade B+');

  const minPb = num(v.min_pullback_bars) ?? 1;
  const maxPb = num(v.max_pullback_bars) ?? 3;
  const bars = minPb === maxPb ? `${minPb}` : `${minPb}–${maxPb}`;
  const tol = num(v.ema_tol) ? ` (−${trim(num(v.ema_tol)!)}%)` : '';
  const setup = `Leg ≥ ${trim(num(v.leg_pct) ?? 0)}% to a new high${v.require_hod ? ' of day' : ''} · ${bars} candles hold the `
    + `${num(v.ema_period)} EMA${tol} and give back < ${trim(num(v.max_retrace) ?? 0)}% of the leg`
    + (v.macd_positive ? ' · MACD above zero' : '');

  const entry = `Over the last pullback candle's high +${money(num(v.entry_offset) ?? 0)} · arms `
    + `${v.session_start}–${v.entry_cutoff} · only when the tape says GO`;

  const target = v.target_mode === 'fixed'
    ? `target 1 entry + ${money(num(v.target_fixed) ?? 0)}`
    : `target 1 the leg high or ${trim(num(v.target_r) ?? 0)}R`;
  const trade = `Risk ${money(num(v.min_stop) ?? 0)}–${money(num(v.stop_cap) ?? 0).replace('$', '')} · ${target} · `
    + `bot ${v.bot_window_start}–${v.bot_window_end}, ${num(v.bot_entries_per_day)} a day`;
  return [['Stock', stock.join(' · ')], ['Setup', setup], ['Entry', entry], ['Trade', trade]];
}

function universeLine(v: Values): string {
  const parts = [range(num(v.min_price), num(v.max_price), px, 'price') ?? 'any price', `gap ≥ ${trim(num(v.min_gap_pct) ?? 0)}%`,
    `pre-market RVOL ≥ ${trim(num(v.min_pm_rvol) ?? 0)}x`];
  if (v.require_news) parts.push('news');
  return parts.join(' · ');
}

function researchTrade(v: Values): string {
  return `Risk ${money(num(v.min_stop) ?? 0)}–${money(num(v.stop_cap) ?? 0).replace('$', '')} · target `
    + `${trim(num(v.target_r) ?? 0)}R · out after ${num(v.bailout_bars)} bars`;
}

/** The setup card's rule lines, from the template in play. */
export function ruleLines(setup: string, v: Values): [string, string][] {
  switch (setup) {
    case 'first_pullback':
      return firstPullbackLines(v);
    case 'flat_top_breakout':
      return [
        ['Stock', universeLine(v)],
        ['Setup', `Impulse ≥ ${trim(num(v.ft_impulse_pct) ?? 0)}% into the high of day · ${num(v.ft_min_consol)}–`
          + `${num(v.ft_max_consol)} tight candles within ${trim(num(v.ft_band) ?? 0)}%`],
        ['Entry', `${v.ft_entry === 'break' ? 'The break of the high' : `A green candle holding over the high within ${num(v.ft_hold_bars)} bars`}`
          + ` · ${v.session_start}–${v.entry_cutoff}`],
        ['Trade', researchTrade(v)],
      ];
    case 'red_to_green':
      return [
        ['Stock', universeLine(v)],
        ['Setup', `≥ ${num(v.r2g_min_red_bars)} close under the open, then back through it by ${v.r2g_cutoff}`],
        ['Trade', `${researchTrade(v)}${v.r2g_target_hod ? ' (or the high of day)' : ''}`],
      ];
    case 'gap_and_go':
      return [
        ['Stock', `Top ${num(v.top)} by pre-market RVOL · ${universeLine(v)}`],
        ['Entry', `Buy stop at the pre-market high until ${v.entry_end}`],
        ['Trade', `Stop ${money(num(v.stop_cents) ?? 0)} or ${trim(num(v.stop_pct) ?? 0)}% · half at ${trim(num(v.t1_r) ?? 0)}R,`
          + ` the rest at ${trim(num(v.t2_r) ?? 0)}R · out ${v.time_stop}`],
      ];
    default:
      return [];
  }
}

/** The tape gate's four verdicts in the template's own numbers. */
export function tapeLines(v: Values): [string, string][] {
  const k = (n: number | null) => (n == null ? '?' : n >= 1000 ? `${trim(n / 1000, 1)}k` : String(n));
  return [
    ['go', `green prints (${num(v.min_ask_prints)}+ at the ask), nothing holding the level`],
    ['wait', `${k(num(v.wall))}+ seller not thinning`],
    ['veto', `spread over ${money(num(v.spread_max) ?? 0)} / ${k(num(v.big_seller))}+ seller`],
    ['blind', 'no Level 2'],
  ];
}

export function readoutText(t: SetupTemplate): string | null {
  const r = t.readout;
  if (!r) return null;
  if (r.state === 'passed') return 'read-out passed';
  if (r.state === 'collecting') return `collecting ${r.go_triggered ?? 0} / ${r.min_go ?? 50}`;
  return r.state.replace('_', ' ');
}
