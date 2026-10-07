/**
 * The five short setups' rule lines (ADR 049), from the template in play: the card says the rules the scanner runs,
 * never words written by hand. A short sells at its entry under the trigger, with a buy stop over the pattern, and
 * covers at R x the risk under the entry. Pure.
 */
import { bars, ema, money, num, stockLine, tradeLine, trim, type Values } from './templateParts';
import type { TemplateBotWindow } from './templateTypes';

/** The stock filter, and what the template does under SSR (a breakdown short's own choice). */
function stockShort(v: Values): string {
  const ssr = v.ssr === 'skip' ? ' · skips SSR' : '';
  return `${stockLine(v)}${ssr}`;
}

function macd(v: Values): string {
  return v.macd_negative ? ' · MACD under zero' : '';
}

/** "Under the last bounce candle's low −$0.01 · buy stop $0.01 over the bounce · arms 09:35–11:30 · ...". */
function entryShort(under: string, stop: string, v: Values): string {
  return `Under ${under} −${money(num(v.entry_offset) ?? 0)} · buy stop ${stop} · arms ${v.session_start}–`
    + `${v.entry_cutoff} · only when the tape says GO`;
}

function stopOver(what: string, v: Values): string {
  return `${money(num(v.stop_offset) ?? 0)} over ${what}`;
}

function cover(v: Values): string {
  return `cover at ${trim(num(v.target_r) ?? 0)}R under the entry`;
}

function backsideLines(v: Values, w?: TemplateBotWindow | null): [string, string][] {
  const setup = `Fade ≥ ${trim(num(v.fade_pct) ?? 0)}% off the high of day to a new ${num(v.fade_lookback)}-candle low · `
    + `${bars(num(v.min_bounce_bars), num(v.max_bounce_bars))} candle bounce under the high, closes under the `
    + `${ema(v)}, taking back < ${trim(num(v.max_retrace) ?? 0)}% of the fade${macd(v)}`;
  return [
    ['Stock', stockShort(v)],
    ['Setup', setup],
    ['Entry', entryShort('the last bounce candle\'s low', stopOver('the bounce', v), v)],
    ['Trade', tradeLine(v, cover(v), w)],
  ];
}

function bearFlagLines(v: Values, w?: TemplateBotWindow | null): [string, string][] {
  const pole = `Pole of ${num(v.pole_min_bars)}+ red candles down ≥ ${trim(num(v.pole_min_pct) ?? 0)}%`
    + (v.pole_volume_rising ? ' on rising volume' : '');
  const flag = `${bars(num(v.min_flag_bars), num(v.max_flag_bars))} candles drift up, taking back ≤ `
    + `${trim(num(v.max_retrace) ?? 0)}% of it` + (v.flag_volume_lighter ? ' on lighter volume' : '')
    + (v.ema_hold ? `, closes under the ${ema(v)}` : '');
  const checks: string[] = [];
  if (v.macd_negative) checks.push('MACD under zero');
  if (v.reject_green_volume_high) checks.push('the day\'s highest-volume candle not green');
  if (num(v.max_pole_wick) != null) checks.push(`pole-bottom wick ≤ ${trim(num(v.max_pole_wick)!)}%`);
  return [
    ['Stock', stockShort(v)],
    ['Setup', [pole, flag, ...checks].join(' · ')],
    ['Entry', entryShort('the last flag candle\'s low', stopOver('the flag', v), v)],
    ['Trade', tradeLine(v, cover(v), w)],
  ];
}

function touchWords(v: Values): string {
  const pct = num(v.touch_pct) ?? 0;
  const dollars = num(v.touch_dollars) ?? 0;
  return dollars > 0 ? `within ${trim(pct)}% or ${money(dollars)} under it` : `within ${trim(pct)}% under it`;
}

function failedBreakoutLines(v: Values, w?: TemplateBotWindow | null): [string, string][] {
  const setup = `A flat top (the high of day) touched ${num(v.min_touches)}+ times in ${num(v.lookback)} candles, a high `
    + `${touchWords(v)} · a poke ≥ ${money(num(v.poke_dollars) ?? 0)} over it · a close back under it within `
    + `${num(v.fail_bars)} candles · breaks down within ${num(v.trigger_bars)}${macd(v)}`;
  return [
    ['Stock', stockShort(v)],
    ['Setup', setup],
    ['Entry', entryShort('the low of the candle that closed back under', stopOver('the poke', v), v)],
    ['Trade', tradeLine(v, cover(v), w)],
  ];
}

function lostVwapLines(v: Values, w?: TemplateBotWindow | null): [string, string][] {
  const dollars = num(v.retest_dollars) ?? 0;
  const near = `within ${trim(num(v.retest_pct) ?? 0)}%${dollars > 0 ? ` or ${money(dollars)}` : ''} of VWAP`;
  const setup = `Over VWAP from ${v.open_at} · a close under it · a retest ${near} that fails · one try a day${macd(v)}`;
  return [
    ['Stock', stockShort(v)],
    ['Setup', setup],
    ['Entry', entryShort('the retest\'s low', `${stopOver('the retest', v)}, or over VWAP when higher`, v)],
    ['Trade', tradeLine(v, cover(v), w)],
  ];
}

function ssrBounceLines(v: Values, w?: TemplateBotWindow | null): [string, string][] {
  const setup = `Under SSR and VWAP · a drop ≥ ${trim(num(v.drop_pct) ?? 0)}% to a new low of day · `
    + `${num(v.bounce_greens)} green candles off it · the level over the price: the break, a round number (every `
    + `${money(num(v.round_step) ?? 0)}), the last lower high or VWAP`;
  const entry = `Rests ${money(num(v.entry_offset) ?? 0)} under the level once the bounce is within `
    + `${trim(num(v.arm_pct) ?? 0)}% of it, so a buyer fills it above the bid · buy stop `
    + `${trim(num(v.stop_pct) ?? 0)}% over the entry (≥ ${money(num(v.stop_min) ?? 0)}) · cancelled after `
    + `${num(v.cancel_min)} min, on a new low or a close over the level · arms ${v.session_start}–${v.entry_cutoff}`;
  return [
    ['Stock', stockLine(v)],
    ['Setup', setup],
    ['Entry', entry],
    ['Trade', tradeLine(v, cover(v), w)],
  ];
}

/** A short setup's rule lines; null for a setup that is not one of the five. */
export function shortRuleLines(setup: string, v: Values, w?: TemplateBotWindow | null): [string, string][] | null {
  switch (setup) {
    case 'backside_lower_high':
      return backsideLines(v, w);
    case 'bear_flag':
      return bearFlagLines(v, w);
    case 'failed_breakout':
      return failedBreakoutLines(v, w);
    case 'lost_vwap':
      return lostVwapLines(v, w);
    case 'ssr_bounce':
      return ssrBounceLines(v, w);
    default:
      return null;
  }
}

/** A short template row's one-line summary of its pattern; null for a setup that is not one of the five. */
export function shortRuleSummary(setup: string, v: Values): string | null {
  switch (setup) {
    case 'backside_lower_high':
      return `▼ Fade ≥ ${trim(num(v.fade_pct) ?? 0)}% · ${bars(num(v.min_bounce_bars), num(v.max_bounce_bars))} `
        + 'bar bounce under the high · buy stop over the bounce';
    case 'bear_flag':
      return `▼ Pole ${num(v.pole_min_bars)}+ red, ≥ ${trim(num(v.pole_min_pct) ?? 0)}% · `
        + `${bars(num(v.min_flag_bars), num(v.max_flag_bars))} bar flag · buy stop over the flag`;
    case 'failed_breakout':
      return `▼ ${num(v.min_touches)}+ touches · a poke over the flat top, back under within ${num(v.fail_bars)} · `
        + 'buy stop over the poke';
    case 'lost_vwap':
      return '▼ Over VWAP from the open · lost it · a retest fails at VWAP · one try a day';
    case 'ssr_bounce':
      return `▼ SSR · drop ≥ ${trim(num(v.drop_pct) ?? 0)}% · rests 1c under the level · cancelled after `
        + `${num(v.cancel_min)} min`;
    default:
      return null;
  }
}
