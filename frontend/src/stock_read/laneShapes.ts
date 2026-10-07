/**
 * A live lane's shapes on a chart pane (ADR 036): its leg, pole, impulse or open, the pullback, flag,
 * base or red phase it forms, and its levels -- the lead lane in colour, the rest faded; a failed one
 * says the rule it broke. ``bar`` is the pane's candle (a minute; the 5-minute lanes' five,
 * ``fiveMinuteShapes.ts``) and ``hoverId`` the id its boxes report under the pointer. The flat top draws its own
 * way (``flatTopShapes.ts``: its touches, the break, the hold). Pure.
 */
import type { Time } from 'lightweight-charts';
import { isShortSetup } from '../constantGroups/short_setups';
import { SETUP_COLORS } from './constants';
import { flatTop5mOnMinute, flatTopShapes, isFlatTop, type LaneDraw } from './flatTopShapes';
import { shortReason } from './pastSetups';
import { formingProgress, fmtPx } from './planMath';
import { shortLaneShapes } from './shortShapes';
import type { SetupLane, SetupLeg, StockPlan } from './types';

/** What drawing a lane needs from a pane. */
export interface LaneDrawOptions {
  /** Epoch seconds -> the pane's nearest bar time; null when the pane has no bars. */
  toTime: (epochSec: number) => Time | null;
  /** Where a leg began, from the pane's candles (the lowest low before its high). */
  legStart?: (leg: SetupLeg) => number;
  /** The high of the pane's candle that starts at an epoch second (a flat top's break), null when it has none. */
  highAt?: (epochSec: number) => number | null;
}

/** The hover id a live lane's boxes carry. */
export function laneHoverId(setupType: string): string {
  return `lane:${setupType}`;
}

const MIN = 60;
const LIVE_DRAWN = new Set(['leg', 'pullback', 'armed', 'near', 'triggered', 'filtered', 'failed']);


function tone(state: StockPlan['state'] | string): { stroke: string; fill: string } {
  if (state === 'triggered') return { stroke: SETUP_COLORS.target, fill: 'rgba(48, 209, 88, 0.12)' };
  if (state === 'armed' || state === 'near' || state === 'manual') return { stroke: SETUP_COLORS.trigger, fill: SETUP_COLORS.leg };
  return { stroke: SETUP_COLORS.formingStroke, fill: SETUP_COLORS.forming };
}

function pct(x: number): string {
  return `${x >= 0 ? '+' : ''}${(x * 100).toFixed(1)}%`;
}

/** The lane's drawable levels: an armed setup's, else what a forming one would arm with. */
export function levelsOf(lane: SetupLane): { trigger: number; stop: number; bars: number; end: number | null } | null {
  if (lane.setup && lane.state !== 'watching') {
    return { trigger: lane.setup.trigger, stop: lane.setup.stop, bars: lane.setup.pullback_bars ?? 0,
      end: lane.setup.armed_bar_t ?? null };
  }
  if (lane.forming) return { trigger: lane.forming.trigger, stop: lane.forming.stop, bars: lane.forming.bars, end: null };
  return null;
}

/** A setup in play on the 1-minute pane: a lane whose pattern reads 5-minute candles (the 5-minute flat top)
 * draws only what this chart trades -- its level, break and 1-minute hold; the 5-minute pane draws the rest. */
export function laneOnMinute(lane: SetupLane, lead: boolean, o: LaneDrawOptions): LaneDraw {
  if (lane.timeframe !== '5m') return laneShapes(lane, lead, o);
  const tag = lane.state === 'failed' ? ` · FAILED: ${shortReason(lane.reason) || 'a rule broke'}` : '';
  return isFlatTop(lane.setup_type) ? flatTop5mOnMinute(lane, lead, o, laneHoverId(lane.setup_type), tag)
    : { boxes: [], segments: [], dots: [], marks: [], words: [] };
}

export function laneShapes(lane: SetupLane, lead: boolean, o: LaneDrawOptions, bar: number = MIN,
  hoverId: string = laneHoverId(lane.setup_type)): LaneDraw {
  const draw: LaneDraw = { boxes: [], segments: [], dots: [], marks: [], words: [] };
  const { boxes, segments } = draw;
  const leg = lane.leg;
  if (!LIVE_DRAWN.has(lane.state) && !lane.forming) return draw;
  // A failed setup stays on the chart faded for as long as the scanner shows it, saying why (once the
  // past setups are read, it is drawn as past instead: `paneDraw`).
  const failed = lane.state === 'failed';
  const bright = lead && !failed;
  const c = bright ? tone(lane.state === 'leg' || lane.state === 'pullback' ? 'forming' : lane.state)
    : { stroke: SETUP_COLORS.fadedStroke, fill: SETUP_COLORS.faded };
  const legFill = bright ? SETUP_COLORS.leg : SETUP_COLORS.faded;
  const legStroke = bright ? SETUP_COLORS.legStroke : SETUP_COLORS.fadedStroke;
  const tag = failed ? ` · FAILED: ${shortReason(lane.reason) || 'a rule broke'}` : '';
  // The flat top has a look of its own: its touches ringed, the base boxed, the break and the hold marked.
  if (isFlatTop(lane.setup_type)) return flatTopShapes(lane, lead, o, bar, hoverId, tag);
  // A short (ADR 049): orange, ▼ SHORT, its trigger under the pattern and its buy stop over it.
  if (lane.side === 'short' || isShortSetup(lane.setup_type)) return shortLaneShapes(lane, lead, o, bar, hoverId, tag);
  const lv = levelsOf(lane);
  const lastT = lane.series?.bars_as_of ?? null;
  const endT = lv?.end ?? lastT;
  const box = (t1s: number, t2s: number, p1: number, p2: number, fill: string, stroke: string, labelText: string,
    dashed = false, labelBelow = false) => {
    const t1 = o.toTime(t1s);
    const t2 = o.toTime(t2s);
    if (t1 === null || t2 === null) return;
    boxes.push({ t1, t2, p1, p2, fill, stroke, dashed, label: labelText, labelColor: stroke, labelBelow, hoverId });
  };
  const type = lane.setup_type;
  const provisional = !lane.setup;
  if (type === 'first_pullback' || type === 'bull_flag') {
    if (leg) {
      const start = type === 'bull_flag' && leg.bars ? leg.t - (leg.bars - 1) * bar : (o.legStart?.(leg) ?? leg.t - 5 * bar);
      box(start, leg.t, leg.low, leg.high, legFill, legStroke, `${type === 'bull_flag' ? 'POLE' : 'LEG'} ${pct(leg.pct)}`);
    }
    const legBoxes = boxes.length;
    if (lv && leg && endT !== null && endT > leg.t) {
      const prog = type === 'bull_flag' ? formingProgress(lane) : null;
      const n = lv.bars ? ` ${lv.bars}` : '';
      box(leg.t + bar, endT, lv.stop, lv.trigger, c.fill, c.stroke,
        `${type === 'bull_flag' ? `FLAG${prog ? ` ${prog}` : n}` : `PULLBACK${n}`}${tag}`, provisional, true);
    }
    // Failed before its flag or pullback was drawn (NCPL 2026-09-29: a pole): the pole says so.
    if (failed && legBoxes === 1 && boxes.length === 1) boxes[0] = { ...boxes[0], label: `${boxes[0].label}${tag}` };
  } else if (type === 'red_to_green' && leg) {
    const t1 = o.toTime(leg.t);
    if (t1 !== null) {
      segments.push({ t1, price: leg.high, color: bright ? SETUP_COLORS.trigger : SETUP_COLORS.fadedStroke, dashed: true,
        label: `OPEN ${fmtPx(leg.high)}` });
    }
    if (lastT !== null && leg.low < leg.high) {
      box(leg.t, lastT, leg.low, leg.high, bright ? SETUP_COLORS.risk : SETUP_COLORS.faded,
        bright ? SETUP_COLORS.stop : SETUP_COLORS.fadedStroke, `RED${leg.bars ? ` ${leg.bars}` : ''}${tag}`, true, true);
    }
  } else if (type === 'gap_and_go' && leg) {
    // The pre-market high is the level: drawn from the candle that set it, forming until the open, then armed.
    const t1 = o.toTime(leg.t);
    if (t1 !== null) segments.push({ t1, price: leg.high, color: c.stroke, dashed: provisional, label: `PMH ${fmtPx(leg.high)}` });
  }
  return draw;
}
