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

/** The stock filter every setup with a scanner reads (the catalogue's _STOCK). */
function stockLine(v: Values): string {
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

function bars(lo: number | null, hi: number | null): string {
  const a = lo ?? 1;
  const b = hi ?? a;
  return a === b ? `${a}` : `${a}–${b}`;
}

function ema(v: Values): string {
  const tol = num(v.ema_tol) ? ` (−${trim(num(v.ema_tol)!)}%)` : '';
  return `${num(v.ema_period)} EMA${tol}`;
}

/** "Over the last pullback candle's high +$0.01 · arms 07:00–11:30 · only when the tape says GO". */
function entryLine(what: string, v: Values, window = true): string {
  const arms = window ? ` · arms ${v.session_start}–${v.entry_cutoff}` : '';
  return `${what} +${money(num(v.entry_offset) ?? 0)}${arms} · only when the tape says GO`;
}

/** Risk band, target 1 and the bot's own window: the same on every setup with a scanner. */
function tradeLine(v: Values, target: string): string {
  return `Risk ${money(num(v.min_stop) ?? 0)}–${money(num(v.stop_cap) ?? 0).replace('$', '')} · ${target} · `
    + `bot ${v.bot_window_start}–${v.bot_window_end}, ${num(v.bot_entries_per_day)} a day`;
}

function fixedTarget(v: Values): string {
  return `target 1 entry + ${money(num(v.target_fixed) ?? 0)}`;
}

function firstPullbackLines(v: Values): [string, string][] {
  const setup = `Leg ≥ ${trim(num(v.leg_pct) ?? 0)}% to a new high${v.require_hod ? ' of day' : ''} · `
    + `${bars(num(v.min_pullback_bars), num(v.max_pullback_bars))} candles hold the ${ema(v)} and give back `
    + `< ${trim(num(v.max_retrace) ?? 0)}% of the leg` + (v.macd_positive ? ' · MACD above zero' : '');
  const target = v.target_mode === 'fixed' ? fixedTarget(v) : `target 1 the leg high or ${trim(num(v.target_r) ?? 0)}R`;
  return [
    ['Stock', stockLine(v)],
    ['Setup', setup],
    ['Entry', entryLine('Over the last pullback candle\'s high', v)],
    ['Trade', tradeLine(v, target)],
  ];
}

function bullFlagLines(v: Values): [string, string][] {
  const dollars = num(v.pole_min_dollars);
  const pole = `Pole of ${num(v.pole_min_bars)}+ green candles up ≥ ${trim(num(v.pole_min_pct) ?? 0)}%`
    + (dollars != null ? ` (or ${money(dollars)})` : '')
    + (v.pole_volume_rising ? ' on rising volume' : '')
    + (v.require_hod ? ' to a new high of day' : '');
  const flag = `${bars(num(v.min_flag_bars), num(v.max_flag_bars))} red candles give back ≤ `
    + `${trim(num(v.max_retrace) ?? 0)}% of it` + (v.flag_volume_lighter ? ' on lighter volume' : '')
    + (v.ema_hold ? `, closes hold the ${ema(v)}` : '');
  const checks: string[] = [];
  if (num(v.ema_touch_pct) != null) checks.push(`flag low within ${trim(num(v.ema_touch_pct)!)}% of the EMA`);
  if (v.macd_positive) checks.push('MACD above zero');
  if (v.reject_red_volume_high) checks.push('the day\'s biggest candle not red');
  if (num(v.max_pole_wick) != null) checks.push(`pole-top wick ≤ ${trim(num(v.max_pole_wick)!)}%`);
  const target = v.target_mode === 'fixed' ? fixedTarget(v)
    : v.target_mode === 'leg' ? 'target 1 the pole high'
      : `target 1 the pole high or ${trim(num(v.target_r) ?? 0)}R`;
  return [
    ['Stock', stockLine(v)],
    ['Setup', [pole, flag, ...checks].join(' · ')],
    ['Entry', entryLine('Over the last flag candle\'s high', v)],
    ['Trade', tradeLine(v, target)],
  ];
}

function flatTopLines(v: Values): [string, string][] {
  const setup = `Impulse ≥ ${trim(num(v.ft_impulse_pct) ?? 0)}% into the high of day · `
    + `${bars(num(v.ft_min_consol), num(v.ft_max_consol))} candles close within ${trim(num(v.ft_band) ?? 0)}% under it, `
    + `lows over the ${ema(v)}` + (v.macd_positive ? ' · MACD above zero' : '');
  const entry = v.ft_entry === 'break'
    ? entryLine('The break of the high', v)
    : `A green candle holding over the high within ${num(v.ft_hold_bars)} candles, at its close `
      + `+${money(num(v.entry_offset) ?? 0)} · arms ${v.session_start}–${v.entry_cutoff} · only when the tape says GO`;
  const target = v.target_mode === 'fixed' ? fixedTarget(v) : `target 1 ${trim(num(v.target_r) ?? 0)}R`;
  return [['Stock', stockLine(v)], ['Setup', setup], ['Entry', entry], ['Trade', tradeLine(v, target)]];
}

function redToGreenLines(v: Values): [string, string][] {
  const red = num(v.r2g_min_red_bars) ?? 1;
  const setup = `${red}+ close${red === 1 ? '' : 's'} under the ${v.session_start} open, then back through it by `
    + `${v.r2g_cutoff} · one try a day` + (v.macd_positive ? ' · MACD above zero' : '');
  const target = `target 1 ${trim(num(v.target_r) ?? 0)}R${v.r2g_target_hod ? ' or the high of day, whichever is higher' : ''}`;
  return [
    ['Stock', stockLine(v)],
    ['Setup', setup],
    ['Entry', entryLine('Over the open', v, false)],
    ['Trade', tradeLine(v, target)],
  ];
}

function universeLine(v: Values): string {
  const parts = [range(num(v.min_price), num(v.max_price), px, 'price') ?? 'any price', `gap ≥ ${trim(num(v.min_gap_pct) ?? 0)}%`,
    `pre-market RVOL ≥ ${trim(num(v.min_pm_rvol) ?? 0)}x`];
  if (v.require_news) parts.push('news');
  return parts.join(' · ');
}

/** The setup card's rule lines, from the template in play. */
export function ruleLines(setup: string, v: Values): [string, string][] {
  switch (setup) {
    case 'first_pullback':
      return firstPullbackLines(v);
    case 'bull_flag':
      return bullFlagLines(v);
    case 'flat_top_breakout':
      return flatTopLines(v);
    case 'red_to_green':
      return redToGreenLines(v);
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

/** The template row's one-line summary of the pattern ("Leg ≥ 5% · 1–3 bar pullback · stop at the pullback low"). */
export function ruleSummary(setup: string, v: Values): string {
  switch (setup) {
    case 'first_pullback':
      return `Leg ≥ ${trim(num(v.leg_pct) ?? 0)}% · ${bars(num(v.min_pullback_bars), num(v.max_pullback_bars))} bar pullback · stop at the pullback low`;
    case 'bull_flag':
      return `Pole ${num(v.pole_min_bars)}+ green, ≥ ${trim(num(v.pole_min_pct) ?? 0)}% · `
        + `${bars(num(v.min_flag_bars), num(v.max_flag_bars))} bar flag · stop at the flag low`;
    case 'flat_top_breakout':
      return `${bars(num(v.ft_min_consol), num(v.ft_max_consol))} bar base within ${trim(num(v.ft_band) ?? 0)}% of the high · `
        + (v.ft_entry === 'break' ? 'buy the break' : 'buy a green hold over it');
    case 'red_to_green':
      return `${num(v.r2g_min_red_bars) ?? 1}+ red under the ${v.session_start} open · reclaim by ${v.r2g_cutoff}`;
    default:
      return '';
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
