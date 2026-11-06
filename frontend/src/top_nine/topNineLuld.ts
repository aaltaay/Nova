/**
 * Nova's LULD band on a Top 9 tile (operator ask, 2026-10-27: "can we draw the luld on these charts?"; approved
 * mockup). Pure: the day's steps (`GET /api/luld/{symbol}/trail`, the Trader's 1-minute band) and the tile's price
 * scale in; the band's line pieces and its two tags out.
 *
 * Each step holds from its `ts` until the next one's (the last until the trail's `as_of`) and starts at its share of
 * its minute, like the Trader's 1-minute chart (stock_read/luldShapes). A step without a band (a halt, the close) draws
 * nothing. A piece out of the price area is not drawn; the band in force always gets its tags, held at the edge when
 * out of view, so the distance to the halt line shows. Approximate (`exact` false, or the tier a guess) is dashed and
 * its tag carries `≈`. The band never widens the price scale: that would flatten every candle on a quiet tile.
 */
import { LULD_APPROX_MARK } from '../constantGroups/luld';
import type { LuldTrail } from '../ibkr';
import { etChartSeconds } from '../tickerChartData';
import { TOP_NINE_LULD_NONE, TOP_NINE_LULD_NO_TAPE } from './topNineConstants';

export interface LuldScale {
  /** First minute shown (ET wall-clock seconds / 60) and the chart's minute width. */
  startMin: number;
  left: number;
  right: number;
  slot: number;
  top: number;
  bottom: number;
  yOf: (price: number) => number;
}

export interface LuldPiece {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  dashed: boolean;
}

export interface LuldTag {
  side: 'up' | 'down';
  y: number;
  label: string;
  dashed: boolean;
}

export interface TopNineLuldShape {
  pieces: LuldPiece[];
  tags: LuldTag[];
  /** No band to draw: the words that say why (the full reason goes in the hover). */
  none: { text: string; why: string } | null;
}

const TAG_GAP = 18;

function fmt(price: number): string {
  return price < 1 ? price.toFixed(4) : price.toFixed(2);
}

export function topNineLuldShape(trail: LuldTrail | null, scale: LuldScale, lastY: number | null): TopNineLuldShape | null {
  if (!trail) return null;
  const banded = trail.steps.some((s) => s.lower != null || s.upper != null);
  if (!banded) {
    const why = trail.reason ?? trail.state;
    const text = /holds no tape line/i.test(why) ? TOP_NINE_LULD_NO_TAPE : TOP_NINE_LULD_NONE;
    return { pieces: [], tags: [], none: { text, why } };
  }

  const xAt = (epochSec: number) => {
    const min = etChartSeconds(epochSec * 1000) / 60;
    return Math.max(scale.left, Math.min(scale.right, scale.left + (min - scale.startMin) * scale.slot));
  };
  const inView = (y: number) => y >= scale.top && y <= scale.bottom;
  const clampY = (y: number) => Math.max(scale.top, Math.min(scale.bottom, y));

  const pieces: LuldPiece[] = [];
  const steps = trail.steps;
  for (let i = 0; i < steps.length; i += 1) {
    const s = steps[i];
    const x1 = xAt(s.ts);
    const x2 = xAt(i + 1 < steps.length ? steps[i + 1].ts : trail.as_of);
    const dashed = !s.exact || !trail.tier_sure;
    const prev = i > 0 ? steps[i - 1] : null;
    for (const key of ['upper', 'lower'] as const) {
      const price = s[key];
      if (price == null) continue;
      const y = scale.yOf(price);
      if (x2 > x1 && inView(y)) pieces.push({ x1, y1: y, x2, y2: y, dashed });
      // The step: a vertical join from the band before, where either end shows.
      const before = prev?.[key];
      if (before != null && x1 > scale.left) {
        const yb = scale.yOf(before);
        if (inView(y) || inView(yb)) pieces.push({ x1, y1: clampY(yb), x2: x1, y2: clampY(y), dashed });
      }
    }
  }

  // A tag on the last-price tag moves off it: away from the price (up for the upper band), or the other way when
  // the edge leaves no room.
  const clearOf = (y: number, away: 1 | -1): number => {
    if (lastY == null || Math.abs(y - lastY) >= TAG_GAP) return y;
    const first = lastY + away * TAG_GAP;
    return inView(first) ? first : lastY - away * TAG_GAP;
  };
  const tags: LuldTag[] = [];
  const now = steps[steps.length - 1];
  const dashed = !now.exact || !trail.tier_sure;
  const mark = dashed ? LULD_APPROX_MARK : '';
  if (now.upper != null) {
    const y = clearOf(clampY(scale.yOf(now.upper)), -1);
    tags.push({ side: 'up', y, label: `▲ ${mark}${fmt(now.upper)}`, dashed });
  }
  if (now.lower != null) {
    const y = clearOf(clampY(scale.yOf(now.lower)), 1);
    tags.push({ side: 'down', y, label: `▼ ${mark}${fmt(now.lower)}`, dashed });
  }
  return { pieces, tags, none: null };
}
