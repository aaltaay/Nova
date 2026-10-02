/**
 * The setups that ended, drawn on the 1-minute pane where they happened (ADR 036 amendment, operator
 * ask 2026-09-29): each one's leg / pole / impulse / open, and its pullback / flag / base from the leg's
 * high to the candle it died on (or triggered on), between the low it would have stopped at and the high
 * it was building under -- fainter than the live lane, dashed, and labelled with how it ended and what
 * came next (`pastSetups.ts` has the words). Pure: episodes in, boxes out; every box carries its hover id.
 * Every label makes room (`sceneLabels.ts`): a trigger's result first, then the newest setup's, and how
 * one ended before any leg.
 */
import { PAST_COLORS } from './constants';
import type { SceneBox } from './sceneTypes';
import { endOf, pastIconLabel, pastLabel, pastShortLabel, type Episode } from './pastSetups';
import type { LabelShrink } from './sceneLabels';
import type { SetupLeg } from './types';
import type { Time } from 'lightweight-charts';

const MIN = 60;
/** A label's claim to the room: a trigger's result, then how any ended, then the legs -- each the newest
 * first (by epoch seconds). */
const RANK_TRIGGERED = 3e10;
const RANK_OUTCOME = 2e10;
const RANK_LEG = 1e10;

export interface PastDrawOptions {
  /** Epoch seconds -> the pane's nearest bar time; null when the pane has no bar there. */
  toTime: (epochSec: number) => Time | null;
  /** Where a leg began, from the pane's candles. */
  legStart?: (leg: SetupLeg) => number;
  /** The pane's candle in seconds: a minute, or a 5-minute setup's five (`fiveMinuteShapes.ts`). */
  barSec?: number;
}

/** The hover id a past setup's boxes carry. */
export function pastHoverId(ep: Episode): string {
  return `past:${ep.id}`;
}

function pct(x: number): string {
  return `${x >= 0 ? '+' : ''}${(x * 100).toFixed(1)}%`;
}

/** The candle it ended on: the trigger's for a triggered setup, else the one it died on. */
function endBar(ep: Episode, bar: number): number | null {
  if (endOf(ep) === 'triggered') {
    const t = ep.triggered_at ?? ep.ended_at;
    return t === null ? null : Math.floor(t / bar) * bar;
  }
  return ep.died_bar_t ?? (ep.ended_at === null ? null : Math.floor(ep.ended_at / bar) * bar);
}

export function pastShapes(episodes: Episode[], o: PastDrawOptions): SceneBox[] {
  const boxes: SceneBox[] = [];
  const bar = o.barSec ?? MIN;
  for (const ep of episodes) {
    const how = endOf(ep);
    if (!how || how === 'cut') continue;
    const tone = PAST_COLORS[how];
    const legTone = PAST_COLORS.leg;
    const hoverId = pastHoverId(ep);
    const endSec = ep.ended_at ?? ep.died_at ?? ep.triggered_at ?? ep.started_at;
    // The outcome's label shrinks to a few words, then to its marks; the leg's says nothing when crowded.
    const outcome: LabelShrink = { short: pastShortLabel(ep), icon: pastIconLabel(ep),
      rank: (how === 'triggered' ? RANK_TRIGGERED : RANK_OUTCOME) + endSec };
    const legOnly: LabelShrink = { short: null, icon: null, rank: RANK_LEG + endSec };
    const box = (t1s: number, t2s: number, p1: number, p2: number, fill: string, stroke: string, label: string,
      labelColor: string, shrink: LabelShrink, labelBelow = false) => {
      const t1 = o.toTime(t1s);
      const t2 = o.toTime(Math.max(t1s, t2s));
      if (t1 === null || t2 === null) return;
      boxes.push({ t1, t2, p1, p2, fill, stroke, dashed: true, label, labelColor, labelBelow, shrink, hoverId });
    };
    const leg = ep.leg;
    const end = endBar(ep, bar) ?? leg.t;
    const high = ep.setup?.trigger ?? ep.after?.level ?? leg.high;
    const low = ep.setup?.stop ?? ep.after?.floor ?? null;
    const label = pastLabel(ep);
    const type = ep.setup_type;
    if (type === 'first_pullback' || type === 'bull_flag') {
      const start = type === 'bull_flag' && leg.bars ? leg.t - (leg.bars - 1) * bar : (o.legStart?.(leg) ?? leg.t - 5 * bar);
      const legLabel = `${type === 'bull_flag' ? 'POLE' : 'LEG'} ${pct(leg.pct)}`;
      if (low !== null && end > leg.t) {
        box(start, leg.t, leg.low, leg.high, legTone.fill, legTone.stroke, legLabel, legTone.ink, legOnly);
        box(leg.t + bar, end, low, high, tone.fill, tone.stroke, label, tone.ink, outcome, true);
      } else {
        box(start, leg.t, leg.low, leg.high, tone.fill, tone.stroke, `${legLabel} · ${label}`, tone.ink, outcome);
      }
    } else if (type === 'flat_top_breakout') {
      box(leg.t, end, low ?? high, high, tone.fill, tone.stroke, `BASE · ${label}`, tone.ink, outcome, true);
    } else if (type === 'red_to_green') {
      box(leg.t, end, low ?? leg.low, leg.high, tone.fill, tone.stroke, `RED${leg.bars ? ` ${leg.bars}` : ''} · ${label}`,
        tone.ink, outcome, true);
    } else if (type === 'gap_and_go') {
      // From the open (when it armed) to how it ended, between its stop and the pre-market high.
      const openT = ep.setup?.detail?.open_t;
      box(typeof openT === 'number' ? openT : ep.started_at, end, low ?? leg.low, high, tone.fill, tone.stroke,
        `PMH · ${label}`, tone.ink, outcome, true);
    }
  }
  return boxes;
}
