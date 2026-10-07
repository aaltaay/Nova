/**
 * A short setup's live shapes on a chart pane (ADR 049): what it grew from -- the fade, the pole, the flat top it
 * poked over, the VWAP it lost, the drop under SSR -- and the bounce, flag, failure, retest or resting short that
 * arms it, between its trigger (under) and its buy stop (over). Orange, and every label carries ▼ SHORT: VWAP and
 * the Paper chip are orange too, so the colour never speaks alone. The lead lane in colour, the rest faded; a
 * failed one says the rule it broke. `laneShapes.ts` hands a short lane here. Pure.
 */
import { SHORT_SETUP_COLORS } from '../constantGroups/short_setups';
import { SETUP_COLORS } from './constants';
import type { LaneDraw } from './flatTopShapes';
import type { LaneDrawOptions } from './laneShapes';
import { fmtPx } from './planMath';
import type { SetupLane } from './types';

const MIN = 60;
const LIVE_DRAWN = new Set(['leg', 'pullback', 'armed', 'near', 'triggered', 'filtered', 'failed']);

function drop(x: number): string {
  return `−${(Math.abs(x) * 100).toFixed(1)}%`;
}

/** The lane's trigger and buy stop: an armed setup's, else what a forming one would arm with. */
function levels(lane: SetupLane): { trigger: number; stop: number; bars: number; end: number | null } | null {
  if (lane.setup && lane.state !== 'watching') {
    return { trigger: lane.setup.trigger, stop: lane.setup.stop, bars: lane.setup.pullback_bars ?? 0,
      end: lane.setup.armed_bar_t ?? null };
  }
  if (lane.forming) return { trigger: lane.forming.trigger, stop: lane.forming.stop, bars: lane.forming.bars, end: null };
  return null;
}

export function shortLaneShapes(lane: SetupLane, lead: boolean, o: LaneDrawOptions, bar: number = MIN,
  hoverId: string, tag: string): LaneDraw {
  const draw: LaneDraw = { boxes: [], segments: [], dots: [], marks: [], words: [] };
  if (!LIVE_DRAWN.has(lane.state) && !lane.forming) return draw;
  const bright = lead && lane.state !== 'failed';
  const stroke = bright ? SHORT_SETUP_COLORS.stroke : SETUP_COLORS.fadedStroke;
  const fill = bright ? SHORT_SETUP_COLORS.fill : SETUP_COLORS.faded;
  const legFill = bright ? SHORT_SETUP_COLORS.legFill : SETUP_COLORS.faded;
  const legStroke = bright ? SHORT_SETUP_COLORS.legStroke : SETUP_COLORS.fadedStroke;
  const leg = lane.leg;
  const lv = levels(lane);
  const lastT = lane.series?.bars_as_of ?? null;
  const endT = lv?.end ?? lastT;
  const provisional = !lane.setup;
  const box = (t1s: number, t2s: number, p1: number, p2: number, f: string, s: string, label: string, dashed = false,
    labelBelow = false) => {
    const t1 = o.toTime(t1s);
    const t2 = o.toTime(t2s);
    if (t1 === null || t2 === null) return;
    draw.boxes.push({ t1, t2, p1, p2, fill: f, stroke: s, dashed, label, labelColor: s, labelBelow, hoverId });
  };
  const line = (ts: number, price: number, label: string, dashed = true) => {
    const t1 = o.toTime(ts);
    if (t1 !== null) draw.segments.push({ t1, price, color: stroke, dashed, label });
  };
  // The armed part: from the candle after the context to the last one it read, trigger under, buy stop over.
  const armedBox = (word: string, from: number) => {
    if (lv && endT !== null && endT > from) {
      box(from, endT, lv.trigger, lv.stop, fill, stroke, `▼ SHORT · ${word}${tag}`, provisional, true);
    }
  };
  const before = draw.boxes.length;
  switch (lane.setup_type) {
    case 'backside_lower_high':
      if (leg) box(leg.t - 5 * bar, leg.t, leg.low, leg.high, legFill, legStroke, `▼ FADE ${drop(leg.pct)}`);
      if (leg) armedBox(`BOUNCE${lv?.bars ? ` ${lv.bars}` : ''}`, leg.t + bar);
      break;
    case 'bear_flag':
      if (leg) {
        const start = leg.bars ? leg.t - (leg.bars - 1) * bar : leg.t - 3 * bar;
        box(start, leg.t, leg.low, leg.high, legFill, legStroke, `▼ POLE ${drop(leg.pct)}`);
        armedBox(`FLAG${lv?.bars ? ` ${lv.bars}` : ''}`, leg.t + bar);
      }
      break;
    case 'failed_breakout':
      if (leg) {
        const first = leg.touches?.[0]?.[0] ?? leg.t - 10 * bar;
        line(first, leg.low, `FLAT TOP ${fmtPx(leg.low)}`);
        armedBox('FAILED BACK UNDER', leg.t);
      }
      break;
    case 'lost_vwap':
      if (leg) {
        line(leg.t, leg.high, `LOST VWAP ${fmtPx(leg.high)}`);
        armedBox('RETEST', leg.t + bar);
      }
      break;
    case 'ssr_bounce': {
      if (leg) box(leg.t - 5 * bar, leg.t, leg.low, leg.high, legFill, legStroke, `▼ DROP ${drop(leg.pct)} · SSR`);
      const level = lane.setup?.detail?.level;
      if (leg && typeof level === 'number') line(leg.t, level, `LEVEL ${fmtPx(level)}`);
      if (leg && lane.setup) line(lane.setup.armed_bar_t ?? leg.t, lane.setup.trigger,
        `▼ SHORT RESTS ${fmtPx(lane.setup.trigger)}${tag}`, provisional);
      break;
    }
    default:
      break;
  }
  // Failed before its armed part was drawn: the context says so.
  if (tag && draw.boxes.length === before + 1 && !lv) {
    draw.boxes[before] = { ...draw.boxes[before], label: `${draw.boxes[before].label}${tag}` };
  }
  return draw;
}
