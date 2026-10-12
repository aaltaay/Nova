/**
 * The trend lines on the 1- and 5-minute panes (ADR 036 amendment 2026-10-12; operator ask: "When we see an obvious
 * ascending line and descending line, can we have them part of the strategy? Like it show in the chart obvious line
 * for the long and short positions?" -- "It's like what visually make sense, and I think we r gonna need that on the
 * 1min and 5min charts"). Pure. Each pane draws its own chart's lines (`level_map.lines`, read by the backend from
 * the same candles): an ascending support in green, a descending resistance in orange, a ring on each touch; a line
 * that broke stays faint for a few candles, a cross on the candle that closed through it. Its name sits in the
 * pane's edge column where the line runs now and opens its card (`trendStory`). Nothing here is estimated: every
 * point is the backend's.
 */
import type { Time } from 'lightweight-charts';
import { EDGE_PRIORITY } from '../chart';
import { TREND_COLORS } from './constants';
import type { TrendLine } from './levelTypes';
import { fmtPx } from './planMath';
import type { SceneTrend } from './sceneTypes';
import type { ShapeStory } from './ShapeTip';
import { clockEt, hhmmEt } from './timeWords';
import type { StockRead } from './types';

/** `full` the 1-minute pane, `map` the 5-minute. */
export type TrendPane = 'full' | 'map';

const HOME = { full: 'one_minute', map: 'five_minute' } as const;
const CANDLES: Record<TrendLine['home'], string> = { one_minute: '1-minute', five_minute: '5-minute' };

export function trendHoverId(l: TrendLine): string {
  return `trend:${l.id}`;
}

function rgba(hex: string, alpha: number): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

export function trendColor(l: TrendLine, alpha: number = TREND_COLORS.brokenAlpha): string {
  const c = l.kind === 'support' ? TREND_COLORS.support : TREND_COLORS.resistance;
  return l.state === 'broken' ? rgba(c, alpha) : c;
}

/** Its name at the right edge: "↗ support · 4", "↘ resistance broke 09:52". */
export function trendLabel(l: TrendLine): string {
  if (l.state === 'broken' && l.broke) return `${l.tag} broke ${hhmmEt(l.broke.t)}`;
  return `${l.tag} · ${l.touches.length}`;
}

/** The pane's lines on its own bars; a line whose candles the pane does not hold is left out. */
export function trendScene(read: StockRead, pane: TrendPane, toTime: (epochSec: number) => Time | null): SceneTrend[] {
  const out: SceneTrend[] = [];
  for (const l of read.level_map?.lines?.[HOME[pane]] ?? []) {
    const t1 = toTime(l.t1);
    const t2 = toTime(l.t2);
    const tEnd = toTime(l.now_t);
    if (t1 === null || t2 === null || tEnd === null) continue;
    const touches: SceneTrend['touches'] = [];
    for (const x of l.touches) {
      const t = toTime(x.t);
      if (t !== null) touches.push({ t, price: x.p });
    }
    const bt = l.broke ? toTime(l.broke.t) : null;
    out.push({
      t1, p1: l.p1, t2, p2: l.p2, tEnd, pEnd: l.now_p, slope: l.slope,
      color: trendColor(l),
      faded: l.state === 'broken',
      touches,
      broke: l.broke && bt !== null ? { t: bt, price: l.broke.p } : null,
      label: trendLabel(l),
      labelColor: trendColor(l, TREND_COLORS.brokenLabelAlpha),
      hoverId: trendHoverId(l),
      priority: EDGE_PRIORITY.level,
    });
  }
  return out;
}

/** A small move in a few characters: "2.1c", "0.04c", "$1.20". */
export function centsText(x: number): string {
  const v = Math.abs(x);
  if (v >= 1) return `$${v.toFixed(2)}`;
  const c = v * 100;
  return `${c >= 1 ? Number(c.toFixed(1)) : Number(c.toPrecision(2))}c`;
}

function whereWords(l: TrendLine, price: number | null): string {
  if (l.state === 'broken' && l.broke) {
    return `Broke at ${clockEt(l.broke.t)}: a candle closed ${l.kind === 'support' ? 'under' : 'over'} it`;
  }
  if (l.side === 'at') return 'The price is on it now';
  const role = l.kind === 'support' ? 'Support' : 'Resistance';
  if (price === null || price <= 0) return role;
  const d = l.now_p - price;
  const pct = ((Math.abs(d) / price) * 100).toFixed(1);
  return `${role} · $${Math.abs(d).toFixed(2)} ${d > 0 ? 'above' : 'below'} the price (${pct}%)`;
}

function whenWords(l: TrendLine): string {
  const times = l.touches.map(t => t.t);
  if (times.length <= 4) return times.map(clockEt).join(', ');
  return `${clockEt(times[0])} to ${clockEt(times[times.length - 1])}`;
}

/** The card of the line `id` names: what it is, where it runs, how it was drawn and what it means. */
export function trendStory(id: string, read: StockRead): ShapeStory | null {
  const lines = read.level_map?.lines;
  const l = [...(lines?.one_minute ?? []), ...(lines?.five_minute ?? [])].find(x => trendHoverId(x) === id);
  if (!l) return null;
  const up = l.dir === 'up';
  const support = l.kind === 'support';
  const n = l.touches.length;
  const why = [
    `A ${up ? 'rising' : 'falling'} line through the ${CANDLES[l.home]} candles' swing ${support ? 'lows' : 'highs'}: `
      + `they touched it ${n} times (${whenWords(l)})`,
    `No candle closed ${support ? 'under' : 'over'} it from the first touch to the last. A touch may miss it by `
      + `${centsText(l.band)} (0.5% of the price, a cent at least): no stock prints a perfect line`,
    `It ${up ? 'rises' : 'falls'} ${centsText(l.slope)} a candle`,
  ];
  const means = support
    ? ['Support many traders can see: buyers watch it.',
      'A close under it breaks it, a bearish sign, and a broken support line often turns into resistance.']
    : ['Resistance many traders can see: buying right under it buys into the sellers.',
      'A close over it breaks it, and a broken resistance line often turns into support.'];
  if (l.retest_t !== null) {
    means.push(`It was tested from the other side at ${clockEt(l.retest_t)} and turned: the ${l.kind} became `
      + `${support ? 'resistance' : 'support'}.`);
  }
  return {
    title: `${up ? '↗ Ascending' : '↘ Descending'} ${l.kind} · ${fmtPx(l.now_p)}`,
    subtitle: whereWords(l, read.price ?? read.level_map?.price ?? null),
    color: trendColor(l),
    lines: [],
    sections: [
      { head: 'Why it is here', items: why },
      { head: 'What it means', items: means },
      { head: 'Not measured', items: ['How often these lines hold is not measured yet: the line describes, and nothing trades on it.'] },
    ],
  };
}
