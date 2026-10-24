/**
 * The Live Trader bots' numbers in words (ADR 055): dollars, prices, the day's P/L line, the chips of a host's rules,
 * the hovers of its skips, steps and copies, and which of a host's open trades a copy belongs to. Pure.
 */
import {
  LT_LARGE_CAPS,
  LT_SIDES_WORDS,
  LT_TAKE_OPEN_WORDS,
  ltAddsWords,
  ltAllowanceWords,
  ltNewestOf,
  ltSellAllWords,
  ltShortStopWords,
  ltSizeWords,
  ltStepWords,
} from '../constantGroups/live_trader';
import { prose } from './botsPageFormat';
import type { LtEvent, LtHost, LtPosition, LtSettings } from './liveTraderTypes';

export function usd(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—';
  const abs = Math.abs(v);
  const text = abs >= 100 || abs === 0 ? Math.round(abs).toLocaleString('en-US') : abs.toFixed(2);
  return `${v < 0 ? '−' : ''}$${text}`;
}

/** Dollars to the cent at any size: fees are read to the cent. */
export function usd2(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—';
  const text = Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
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

/** The settings as chips, in the approved mockup's order. */
export function ruleChips(st: LtSettings, sellAllAt: string): string[] {
  const sides = st.sides === 'both' ? `${LT_SIDES_WORDS.both} · ${ltShortStopWords(st.short_stop_pct)}` : LT_SIDES_WORDS.long;
  const size = st.lot_usd == null ? [] : [ltSizeWords(st.lot_usd)];
  return [ltStepWords(st.step_usd), ...size, ltAddsWords(st.adds), ltAllowanceWords(st.allowance_usd), sides,
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

/** A reason's first clause, for a line that has room for one: "the Bot switch in the header is off" of "...: bots place
 *  no order". A clock (15:55) is not a clause break. */
export function firstClause(text: string): string {
  return text.split(': ')[0];
}

/** Eastern HH:MM of an epoch second; blank when unknown. */
function etHm(ts: number | null): string {
  if (!ts || !Number.isFinite(ts)) return '';
  return new Date(ts * 1000).toLocaleTimeString('en-US', { timeZone: 'America/New_York', hour12: false, hour: '2-digit', minute: '2-digit' });
}

/** The newest skips, by reason, each with its stocks and times; null with none. `total` is the day's count. */
export function skipsTip(events: readonly LtEvent[], total: number): string | null {
  const skips = events.filter(e => e.outcome === 'skipped');
  if (!skips.length) return null;
  const byWhy = new Map<string, string[]>();
  for (const e of skips) {
    const why = prose(e.text ?? e.code ?? '');
    byWhy.set(why, [...(byWhy.get(why) ?? []), [e.symbol, etHm(e.ts)].filter(Boolean).join(' ')]);
  }
  const lines = [...byWhy].map(([why, what]) => `${why}\n   ${what.join(' · ')}`);
  if (skips.length < total) lines.push(`(${ltNewestOf(skips.length, total)})`);
  return lines.join('\n');
}

/** The newest steps that are not skips (orders, fills, settings), newest first; null with none. */
export function stepsTip(events: readonly LtEvent[]): string | null {
  const steps = events.filter(e => e.outcome !== 'skipped' && e.text);
  if (!steps.length) return null;
  return steps.map(e => `${etHm(e.ts)}  ${prose(e.text)}`.trim()).join('\n');
}

/** Whether the bot's position copies this open trade of its host: its row, else the same stock and side. */
export function copies(p: LtPosition, t: { id: string; symbol: string; side: string }): boolean {
  return p.row_id === t.id || (p.symbol === t.symbol && p.side === t.side);
}

/** A copy the bot holds, in words: shares, its own entry, the host's average, the P/L now. */
export function positionTip(p: LtPosition): string {
  const parts = [`Holds ${p.qty} share${p.qty === 1 ? '' : 's'} of ${p.symbol} ${p.side === 'short' ? 'short' : 'long'}, in at ${px(p.avg_cost)}`];
  if (p.their_avg != null) parts.push(`their average ${px(p.their_avg)}${p.adds_followed ? `, ${p.adds_followed} add${p.adds_followed === 1 ? '' : 's'} followed` : ''}`);
  if (p.now != null) parts.push(`now ${px(p.now)}: ${signedUsd(p.pl_usd)}`);
  if (p.state !== 'open') parts.push(p.state === 'entering' ? 'its entry is working' : 'its close is working');
  return [parts.join(' · '), p.note ? prose(p.note) : null].filter(Boolean).join('\n');
}
