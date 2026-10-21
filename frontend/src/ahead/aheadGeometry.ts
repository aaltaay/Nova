/**
 * Nova's own arithmetic for Ahead (ADR 061), no AI: the 1-minute support and resistance lines carried on from the
 * chart's newest completed candle to where they meet, and the nearest walls above and below the price. It needs no
 * forecaster, so the lines show on every desk. Pure.
 *
 * Clocks: candle times are CHART seconds (Eastern wall time read as UTC, `etChartSeconds`), the stock read's times
 * epoch seconds. Support lines always rise and resistance lines always fall (`backend/stock_read/trend_lines.py`), so
 * two lines either meet ahead or have met already. Their slopes are rounded on the wire, so a meet is "≈".
 */
import { etChartSeconds } from '../tickerChartData';
import { AHEAD_CONTIGUOUS_TAIL, AHEAD_HORIZON, AHEAD_NOT_A_WALL, AHEAD_STEP_SEC, AHEAD_WORDS } from './aheadConstants';
import type { AheadLines, AheadWall } from './aheadTypes';

/** A completed candle on the chart (chart seconds). */
export interface AheadCandle {
  t: number;
  c: number;
}

/** The fields of a stock-read trend line Ahead reads. */
export interface AheadLineIn {
  id: string;
  kind: 'support' | 'resistance';
  state: 'holding' | 'broken';
  /** Epoch seconds of the candle `now_p` belongs to. */
  now_t: number;
  now_p: number;
  /** Price per candle. */
  slope: number;
}

/** The fields of a stock-read level zone Ahead reads. */
export interface AheadZoneIn {
  id: string;
  lo: number;
  hi: number;
  label: string;
  members: { kind: string }[];
}

// ---------------------------------------------------------------- clocks

export function chartSec(epochSec: number): number {
  return etChartSeconds(epochSec * 1000);
}

/** Back from chart seconds to epoch seconds (exact away from the two clock-change hours). */
export function chartToEpoch(chart: number): number {
  const offsetAt = (x: number) => etChartSeconds(Math.floor(x) * 1000) - Math.floor(x);
  const first = chart - offsetAt(chart);
  return chart - offsetAt(first);
}

/** "09:13" for a chart-seconds time (its UTC reading is the Eastern wall clock). */
export function chartHhmm(chart: number): string {
  return new Date(Math.round(chart) * 1000).toISOString().slice(11, 16);
}

export function etHhmm(epochSec: number): string {
  return chartHhmm(chartSec(epochSec));
}

/** How many of the newest candles are consecutive minutes (1 for a lone candle, 0 for none). */
export function contiguousTail(candles: readonly AheadCandle[]): number {
  if (candles.length === 0) return 0;
  let n = 1;
  for (let i = candles.length - 1; i > 0; i -= 1) {
    if (candles[i].t - candles[i - 1].t !== AHEAD_STEP_SEC) break;
    n += 1;
  }
  return n;
}

/** Candles from a line's own candle to the anchor: the chart's candles in (from, anchor]. A line read from a candle
 * the chart has not drawn yet (the read ran ahead of the chart) counts back in minutes. */
export function candlesSince(candles: readonly AheadCandle[], fromChart: number): number {
  if (candles.length === 0) return 0;
  const anchor = candles[candles.length - 1].t;
  if (fromChart > anchor) return -Math.round((fromChart - anchor) / AHEAD_STEP_SEC);
  let n = 0;
  for (let i = candles.length - 1; i >= 0 && candles[i].t > fromChart; i -= 1) n += 1;
  return n;
}

// ---------------------------------------------------------------- lines to the meet

function none(reason: string): AheadLines {
  return {
    state: 'none', reason, supportId: null, resistanceId: null, supportP: null, resistanceP: null,
    supportSlope: null, resistanceSlope: null, meet: null,
  };
}

/**
 * Carry the holding support under the newest close (the highest) and the holding resistance over it (the lowest) on
 * from the chart's newest completed candle. `tailOk`: the stock trades every minute, so the meet is told as a clock
 * time; otherwise in candles. With no such pair, a holding support carried above a holding resistance at the anchor
 * means the two met behind the newest candle (support rises, resistance falls), and that is what is said.
 */
export function linesToMeet(
  lines: readonly AheadLineIn[], candles: readonly AheadCandle[], tailOk: boolean, horizon = AHEAD_HORIZON,
): AheadLines {
  if (candles.length === 0) return none(AHEAD_WORDS.noCandles);
  const anchor = candles[candles.length - 1];
  const at = (l: AheadLineIn) => l.now_p + l.slope * candlesSince(candles, chartSec(l.now_t));
  type At = { l: AheadLineIn; p: number };
  const pair = (sl: At, rl: At) => ({
    supportId: sl.l.id, resistanceId: rl.l.id, supportP: sl.p, resistanceP: rl.p,
    supportSlope: sl.l.slope, resistanceSlope: rl.l.slope,
  });
  let s: At | null = null;
  let r: At | null = null;
  let sTop: At | null = null;
  let rBottom: At | null = null;
  for (const l of lines) {
    if (l.state !== 'holding' || !Number.isFinite(l.now_p) || !Number.isFinite(l.slope)) continue;
    const p = at(l);
    if (l.kind === 'support' && (sTop === null || p > sTop.p)) sTop = { l, p };
    if (l.kind === 'resistance' && (rBottom === null || p < rBottom.p)) rBottom = { l, p };
    if (l.kind === 'support' && p <= anchor.c && (s === null || p > s.p)) s = { l, p };
    if (l.kind === 'resistance' && p >= anchor.c && (r === null || p < r.p)) r = { l, p };
  }
  // No pair either side of the price: a support carried over a resistance means they met behind the anchor.
  if ((s === null || r === null) && sTop !== null && rBottom !== null && sTop.p > rBottom.p) {
    return { ...pair(sTop, rBottom), state: 'past', reason: AHEAD_WORDS.linesMet, meet: null };
  }
  if (s === null && r === null) return none(AHEAD_WORDS.linesNone);
  if (s === null) return none(AHEAD_WORDS.linesNoSupport);
  if (r === null) return none(AHEAD_WORDS.linesNoResistance);
  const base = pair(s, r);
  if (r.p <= s.p) return { ...base, state: 'past', reason: AHEAD_WORDS.linesMet, meet: null };
  const closing = s.l.slope - r.l.slope;
  if (!(closing > 1e-12)) return { ...base, state: 'none', reason: AHEAD_WORDS.linesNotClosing, meet: null };
  const kc = (r.p - s.p) / closing;
  return {
    ...base,
    state: 'meet',
    reason: null,
    meet: {
      inCandles: kc,
      t: tailOk ? chartToEpoch(anchor.t + AHEAD_STEP_SEC * kc) : null,
      p: s.p + s.l.slope * kc,
      withinZone: kc <= horizon,
    },
  };
}

/** The meet is told as a clock time when the stock's newest candles are consecutive minutes. */
export function meetTailOk(answerTail: number | null, candles: readonly AheadCandle[]): boolean {
  return (answerTail ?? contiguousTail(candles)) >= AHEAD_CONTIGUOUS_TAIL;
}

// ---------------------------------------------------------------- walls

/** A zone is a wall when one of its reasons comes from the candles (not only a round number or VWAP). */
export function isWall(z: AheadZoneIn): boolean {
  return z.members.some((m) => !AHEAD_NOT_A_WALL.includes(m.kind));
}

/** The nearest wall above (its low edge over the price) and below (its high edge under it); a zone holding the price
 * is neither. Null when the two would overlap. */
export function nearestWalls(
  zones: readonly AheadZoneIn[], price: number,
): { above: AheadWall | null; below: AheadWall | null; reason: string | null } {
  let above: AheadWall | null = null;
  let below: AheadWall | null = null;
  for (const z of zones) {
    if (!isWall(z)) continue;
    if (z.lo > price && (above === null || z.lo < above.price)) above = { zoneId: z.id, price: z.lo, label: z.label };
    if (z.hi < price && (below === null || z.hi > below.price)) below = { zoneId: z.id, price: z.hi, label: z.label };
  }
  if (above !== null && below !== null && above.price <= below.price) {
    return { above: null, below: null, reason: AHEAD_WORDS.wallsOverlap };
  }
  return { above, below, reason: above === null && below === null ? AHEAD_WORDS.noWalls : null };
}
