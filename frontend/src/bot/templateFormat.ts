/**
 * A template's numbers in words (ADR 029): the setup card's rule lines and the
 * editor's values are built from the parameters the scanner runs on, never
 * written by hand, so the card cannot say a rule the scanner does not keep.
 * Pure.
 */
import { shortRuleLines, shortRuleSummary } from './templateFormatShort';
import { bars, ema, money, num, stockLine, tradeLine, trim, type Values } from './templateParts';
import type { ParamSpec, ParamValue, SetupTemplate, TemplateBotWindow } from './templateTypes';

export { money };

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

/** "Over the last pullback candle's high +$0.01 · arms 07:00–11:30 · only when the tape says GO". */
function entryLine(what: string, v: Values, window = true): string {
  const arms = window ? ` · arms ${v.session_start}–${v.entry_cutoff}` : '';
  return `${what} +${money(num(v.entry_offset) ?? 0)}${arms} · only when the tape says GO`;
}

function fixedTarget(v: Values): string {
  return `target 1 entry + ${money(num(v.target_fixed) ?? 0)}`;
}

function firstPullbackLines(v: Values, w?: TemplateBotWindow | null): [string, string][] {
  const setup = `Leg ≥ ${trim(num(v.leg_pct) ?? 0)}% to a new high${v.require_hod ? ' of day' : ''} · `
    + `${bars(num(v.min_pullback_bars), num(v.max_pullback_bars))} candles hold the ${ema(v)} and give back `
    + `< ${trim(num(v.max_retrace) ?? 0)}% of the leg` + (v.macd_positive ? ' · MACD above zero' : '');
  const target = v.target_mode === 'fixed' ? fixedTarget(v) : `target 1 the leg high or ${trim(num(v.target_r) ?? 0)}R`;
  return [
    ['Stock', stockLine(v)],
    ['Setup', setup],
    ['Entry', entryLine('Over the last pullback candle\'s high', v)],
    ['Trade', tradeLine(v, target, w)],
  ];
}

function bullFlagLines(v: Values, w?: TemplateBotWindow | null): [string, string][] {
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
    ['Trade', tradeLine(v, target, w)],
  ];
}

/** Where a high touched the flat top (2026-10-06): within the share or the cents under it, whichever is more. */
function touchZone(v: Values): string {
  const pct = num(v.ft_touch_pct) ?? 0;
  const dollars = num(v.ft_touch_dollars) ?? 0;
  if (pct <= 0 && dollars <= 0) return 'at the high itself';
  if (pct <= 0) return `within ${money(dollars)} under it`;
  if (dollars <= 0) return `within ${trim(pct)}% under it`;
  return `within ${trim(pct)}% or ${money(dollars)} under it`;
}

/** The flat top's lines; ``five``: the 5-minute flat top (its pattern on 5-minute candles, the hold on the minutes). */
function flatTopLines(v: Values, w?: TemplateBotWindow | null, five = false): [string, string][] {
  const touches = num(v.ft_min_touches) ?? 1;
  const base = `${bars(num(v.ft_min_consol), num(v.ft_max_consol))} ${five ? '5-minute ' : ''}candles close within `
    + `${trim(num(v.ft_band) ?? 0)}% under it, lows over the ${ema(v)}`;
  // The research's P2 (`last_high`) counts no touches: the base right after the last candle at the high.
  const setup = `Impulse ≥ ${trim(num(v.ft_impulse_pct) ?? 0)}% into the high of day · `
    + (v.ft_base_start === 'last_high' ? base
      : `tapped ${touches}+ time${touches === 1 ? '' : 's'}, a high ${touchZone(v)} · from the first touch, ${base}`)
    + (v.macd_positive ? ' · MACD above zero' : '');
  const hold = five
    ? `A green 1-minute candle that holds it and closes over the high within ${num(v.ft_hold_bars)} minutes of the `
      + `break, at its close +${money(num(v.entry_offset) ?? 0)} · stop `
      + `${v.ft_hold_stop === 'candle' ? 'its low' : 'the pullback\'s low'}`
    : `A green candle that holds it and closes over the high within ${num(v.ft_hold_bars)} candles, at its close `
      + `+${money(num(v.entry_offset) ?? 0)}`;
  const entry = v.ft_entry === 'break'
    ? entryLine('The break of the high', v)
    : `${hold} · arms ${v.session_start}–${v.entry_cutoff} · only when the tape says GO`;
  const target = v.target_mode === 'fixed' ? fixedTarget(v) : `target 1 ${trim(num(v.target_r) ?? 0)}R`;
  return [['Stock', stockLine(v)], ['Setup', setup], ['Entry', entry], ['Trade', tradeLine(v, target, w)]];
}

function redToGreenLines(v: Values, w?: TemplateBotWindow | null): [string, string][] {
  const red = num(v.r2g_min_red_bars) ?? 1;
  const setup = `${red}+ close${red === 1 ? '' : 's'} under the ${v.session_start} open, then back through it by `
    + `${v.r2g_cutoff} · one try a day` + (v.macd_positive ? ' · MACD above zero' : '');
  const target = `target 1 ${trim(num(v.target_r) ?? 0)}R${v.r2g_target_hod ? ' or the high of day, whichever is higher' : ''}`;
  return [
    ['Stock', stockLine(v)],
    ['Setup', setup],
    ['Entry', entryLine('Over the open', v, false)],
    ['Trade', tradeLine(v, target, w)],
  ];
}

function gapAndGoLines(v: Values, w?: TemplateBotWindow | null): [string, string][] {
  const setup = `The pre-market high (candles before ${v.session_start}) · the open under it, then a price over it by `
    + `${v.entry_cutoff} · a gap through it skips the day · one try a day` + (v.macd_positive ? ' · MACD above zero' : '');
  const stop = `stop ${money(num(v.stop_cents) ?? 0)} or ${trim(num(v.stop_pct) ?? 0)}% under the entry, whichever is smaller`;
  const start = w?.start ?? v.bot_window_start;
  const end = w?.end ?? v.bot_window_end;
  const trade = `${stop} · target 1 ${trim(num(v.target_r) ?? 0)}R · bot ${start}–${end}`
    + `${w?.clipped ? ' (clipped to the arming window)' : ''}`;
  return [
    ['Stock', stockLine(v)],
    ['Setup', setup],
    ['Entry', entryLine('Over the pre-market high', v, false)],
    ['Trade', trade],
  ];
}

/** The setup card's rule lines, from the template in play (and its bot window, when the API sends it). */
export function ruleLines(setup: string, v: Values, botWindow?: TemplateBotWindow | null): [string, string][] {
  switch (setup) {
    case 'first_pullback':
      return firstPullbackLines(v, botWindow);
    case 'bull_flag':
      return bullFlagLines(v, botWindow);
    case 'flat_top_breakout':
      return flatTopLines(v, botWindow);
    case 'flat_top_5m':
      return flatTopLines(v, botWindow, true);
    case 'red_to_green':
      return redToGreenLines(v, botWindow);
    case 'gap_and_go':
      return gapAndGoLines(v, botWindow);
    default:
      return shortRuleLines(setup, v, botWindow) ?? [];
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
      return (v.ft_base_start === 'last_high' ? '' : `${num(v.ft_min_touches) ?? 1}+ touches · `)
        + `${bars(num(v.ft_min_consol), num(v.ft_max_consol))} bar base within ${trim(num(v.ft_band) ?? 0)}% of the high · `
        + (v.ft_entry === 'break' ? 'buy the break' : 'buy a green hold over it');
    case 'flat_top_5m':
      return `${num(v.ft_min_touches) ?? 1}+ touches on 5-minute candles · `
        + `${bars(num(v.ft_min_consol), num(v.ft_max_consol))} bar base within ${trim(num(v.ft_band) ?? 0)}% of the high · `
        + (v.ft_entry === 'break' ? 'buy the break' : 'buy a 1-minute hold over it');
    case 'red_to_green':
      return `${num(v.r2g_min_red_bars) ?? 1}+ red under the ${v.session_start} open · reclaim by ${v.r2g_cutoff}`;
    case 'gap_and_go':
      return `Open under the pre-market high · break it by ${v.entry_cutoff} · stop ${money(num(v.stop_cents) ?? 0)} / `
        + `${trim(num(v.stop_pct) ?? 0)}%`;
    default:
      return shortRuleSummary(setup, v) ?? '';
  }
}

/** The tape gate's four verdicts in the template's own numbers; a short's mirrored (ADR 049: its keys are the
 * long's, `big_seller` the buyer that vetoes). */
export function tapeLines(v: Values, side: 'long' | 'short' = 'long'): [string, string][] {
  const k = (n: number | null) => (n == null ? '?' : n >= 1000 ? `${trim(n / 1000, 1)}k` : String(n));
  if (side === 'short') {
    return [
      ['go', `red prints (${num(v.min_ask_prints)}+ at the bid), no buyer holding the level`],
      ['wait', `${k(num(v.wall))}+ buyer not thinning`],
      ['veto', `spread over ${money(num(v.spread_max) ?? 0)} / ${k(num(v.big_seller))}+ buyer`],
      ['blind', 'no Level 2'],
    ];
  }
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
