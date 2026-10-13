/**
 * Nova's LULD band on the 1-minute and 10-second charts (ADR 047 amendments, operator asks 2026-10-12: "i want to see
 * luld lines on the charts", and 2026-10-13: "i want the luld lines show in the 10second charts too"). Pure: the day's
 * steps (`GET /api/luld/{symbol}/trail`) and the pane's candles in; the scene's band line and the band's names at the
 * right edge out.
 *
 * The 5-minute chart does not draw it. The band can move every 30 s, so one 5-minute candle can span several bands.
 * Drawn once per 5-minute candle, candles would poke through the line with no halt, and halt candles would never touch
 * it. Each step starts where its band began: inside its candle, at its share of the candle (`barSec`: 60 on the
 * 1-minute chart, 10 on the 10-second). So a candle that ran into the band meets the band it ran into. A stretch with
 * no candle puts the step between the candles around it. A step with no band (a halt, the close) draws nothing. An
 * approximate step is dashed and its name carries `≈`, so an estimate never looks official.
 */
import { EDGE_PRIORITY, type SeriesTimeIndex } from '../chart';
import { LULD_APPROX_MARK, LULD_COLOR, LULD_LABEL } from '../constantGroups/luld';
import { fmtBand, type LuldTrail } from '../ibkr';
import { etChartSeconds } from '../tickerChartData';
import type { SceneAt, SceneLuld, SceneLuldStep, SceneWord } from './sceneTypes';

/** The band's names in the edge column: over VWAP's and the levels', under the plan's lines. */
const WORD_PRIORITY = EDGE_PRIORITY.vwap + 5;
const MINUTE_SEC = 60;

/**
 * Where an epoch second falls among the pane's candles: in the last candle that starts at or before it, at its share of
 * the candle's `barSec` -- the candle's right edge when the moment is past it (a minute with no candle, or after the
 * newest) -- and the first candle's left edge before the first. Null when the pane has no candles.
 */
export function luldAt(index: SeriesTimeIndex, epochSec: number, barSec = MINUTE_SEC): SceneAt | null {
  const times = index.canonical;
  if (times.length === 0) return null;
  const c = etChartSeconds(epochSec * 1000);
  let lo = 0;
  let hi = times.length - 1;
  let i = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (times[mid] <= c) {
      i = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  if (i < 0) return { t: index.times[0], frac: 0 };
  return { t: index.times[i], frac: Math.min(1, Math.max(0, (c - times[i]) / barSec)) };
}

/** The band line, step by step up to `as_of`; null when there is no band to draw. */
export function luldScene(trail: LuldTrail | null, index: SeriesTimeIndex, barSec = MINUTE_SEC): SceneLuld | null {
  if (!trail || trail.steps.length === 0 || index.times.length === 0) return null;
  const steps: SceneLuldStep[] = [];
  trail.steps.forEach((s, k) => {
    if (s.lower === null && s.upper === null) return;
    const end = k + 1 < trail.steps.length ? trail.steps[k + 1].ts : trail.as_of;
    if (!(end > s.ts)) return;
    const from = luldAt(index, s.ts, barSec);
    const to = luldAt(index, end, barSec);
    if (!from || !to) return;
    steps.push({ from, to, lower: s.lower, upper: s.upper, approx: !s.exact || !trail.tier_sure });
  });
  return steps.length > 0 ? { steps, color: LULD_COLOR } : null;
}

function word(id: string, text: string, price: number): SceneWord {
  return { id, text, color: LULD_COLOR, priority: WORD_PRIORITY, price, series: null, valueWhenOff: false };
}

/**
 * The band in force, named where it sits: `LULD ▲ 6.60` over the price and `LULD ▼ 4.40` under it (`≈` when
 * approximate). Out of view, the column's arrow tag says it, so the distance to the halt line always shows. Nothing
 * while no band is in force (a halt, before 09:30, after 16:00).
 */
export function luldWords(trail: LuldTrail | null): SceneWord[] {
  const now = trail?.steps[trail.steps.length - 1];
  if (!trail || !now) return [];
  const mark = now.exact && trail.tier_sure ? '' : LULD_APPROX_MARK;
  const words: SceneWord[] = [];
  if (now.upper !== null) words.push(word('luld-upper', `${LULD_LABEL} ▲ ${mark}${fmtBand(now.upper)}`, now.upper));
  if (now.lower !== null) words.push(word('luld-lower', `${LULD_LABEL} ▼ ${mark}${fmtBand(now.lower)}`, now.lower));
  return words;
}
