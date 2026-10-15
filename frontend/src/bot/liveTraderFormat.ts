/**
 * The Live Trader cards' numbers in words (ADR 055): dollars, prices, the day's P/L line, the chips of a host's
 * rules, and the shares an approval or a confirmation names. Pure.
 */
import {
  LT_LARGE_CAPS,
  LT_SIDES_WORDS,
  LT_TAKE_OPEN_WORDS,
  ltAddsWords,
  ltAllowanceWords,
  ltSellAllWords,
  ltShortStopWords,
  ltStepWords,
} from '../constantGroups/live_trader';
import type { LtHost, LtSettings } from './liveTraderTypes';

export function usd(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—';
  const abs = Math.abs(v);
  const text = abs >= 100 || abs === 0 ? Math.round(abs).toLocaleString('en-US') : abs.toFixed(2);
  return `${v < 0 ? '−' : ''}$${text}`;
}

export function signedUsd(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—';
  return `${v > 0 ? '+' : v < 0 ? '−' : ''}$${Math.abs(v).toFixed(2)}`;
}

export function px(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—';
  return Math.abs(v) < 1 ? v.toFixed(4) : v.toFixed(2);
}

/** The settings as the card's chips, in the mockup's order. */
export function ruleChips(st: LtSettings, sellAllAt: string): string[] {
  const sides = st.sides === 'both' ? `${LT_SIDES_WORDS.both} · ${ltShortStopWords(st.short_stop_pct)}` : LT_SIDES_WORDS.long;
  return [ltStepWords(st.step_usd), ltAddsWords(st.adds), ltAllowanceWords(st.allowance_usd), sides,
    st.take_open ? LT_TAKE_OPEN_WORDS.take : LT_TAKE_OPEN_WORDS.skip, LT_LARGE_CAPS, ltSellAllWords(sellAllAt)];
}

/** The allowance bar's fill, 0..100. */
export function allowancePct(host: LtHost): number {
  const { used_usd: used, of_usd: of } = host.allowance;
  if (!(of > 0)) return 0;
  return Math.max(0, Math.min(100, Math.round((used / of) * 100)));
}

/** The day's P/L line as SVG points in a `w` x `h` box, from zero; null with fewer than two points. */
export function sparkPoints(series: [number | null, number][], w: number, h: number): { points: string; zeroY: number } | null {
  const ys = [0, ...series.map(p => p[1])];
  if (ys.length < 2) return null;
  const lo = Math.min(...ys);
  const hi = Math.max(...ys);
  const span = hi - lo || 1;
  const step = w / (ys.length - 1);
  const y = (v: number) => Math.round((h - 2 - ((v - lo) / span) * (h - 4)) * 10) / 10;
  return { points: ys.map((v, i) => `${Math.round(i * step)},${y(v)}`).join(' '), zeroY: y(0) };
}

export function secondsLeft(expires: number, now: number): number {
  return Math.max(0, Math.round(expires - now));
}
