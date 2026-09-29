/**
 * The setups that ended, drawn on the 1-minute pane where they happened (ADR 036 amendment, operator
 * ask 2026-09-29): each one's leg / pole / impulse / open, and its pullback / flag / base from the leg's
 * high to the candle it died on (or triggered on), between the low it would have stopped at and the high
 * it was building under -- fainter than the live lane, dashed, and labelled with how it ended and what
 * came next (`pastSetups.ts` has the words). Pure: episodes in, boxes out; every box carries its hover id.
 */
import { PAST_COLORS } from './constants';
import type { SceneBox } from './SetupShapesPrimitive';
import { endOf, pastLabel, type Episode } from './pastSetups';
import type { SetupLeg } from './types';
import type { Time } from 'lightweight-charts';

const MIN = 60;

export interface PastDrawOptions {
  /** Epoch seconds -> the pane's nearest bar time; null when the pane has no bar there. */
  toTime: (epochSec: number) => Time | null;
  /** Where a leg began, from the pane's candles. */
  legStart?: (leg: SetupLeg) => number;
}

/** The hover id a past setup's boxes carry. */
export function pastHoverId(ep: Episode): string {
  return `past:${ep.id}`;
}

function pct(x: number): string {
  return `${x >= 0 ? '+' : ''}${(x * 100).toFixed(1)}%`;
}

/** The candle it ended on: the trigger's for a triggered setup, else the one it died on. */
function endBar(ep: Episode): number | null {
  if (endOf(ep) === 'triggered') {
    const t = ep.triggered_at ?? ep.ended_at;
    return t === null ? null : Math.floor(t / MIN) * MIN;
  }
  return ep.died_bar_t ?? (ep.ended_at === null ? null : Math.floor(ep.ended_at / MIN) * MIN);
}

export function pastShapes(episodes: Episode[], o: PastDrawOptions): SceneBox[] {
  const boxes: SceneBox[] = [];
  for (const ep of episodes) {
    const how = endOf(ep);
    if (!how || how === 'cut') continue;
    const tone = PAST_COLORS[how];
    const legTone = PAST_COLORS.leg;
    const hoverId = pastHoverId(ep);
    const box = (t1s: number, t2s: number, p1: number, p2: number, fill: string, stroke: string, label: string,
      labelColor: string, labelBelow = false) => {
      const t1 = o.toTime(t1s);
      const t2 = o.toTime(Math.max(t1s, t2s));
      if (t1 === null || t2 === null) return;
      boxes.push({ t1, t2, p1, p2, fill, stroke, dashed: true, label, labelColor, labelBelow, hoverId });
    };
    const leg = ep.leg;
    const end = endBar(ep) ?? leg.t;
    const high = ep.setup?.trigger ?? ep.after?.level ?? leg.high;
    const low = ep.setup?.stop ?? ep.after?.floor ?? null;
    const label = pastLabel(ep);
    const type = ep.setup_type;
    if (type === 'first_pullback' || type === 'bull_flag') {
      const start = type === 'bull_flag' && leg.bars ? leg.t - (leg.bars - 1) * MIN : (o.legStart?.(leg) ?? leg.t - 5 * MIN);
      const legLabel = `${type === 'bull_flag' ? 'POLE' : 'LEG'} ${pct(leg.pct)}`;
      if (low !== null && end > leg.t) {
        box(start, leg.t, leg.low, leg.high, legTone.fill, legTone.stroke, legLabel, legTone.ink);
        box(leg.t + MIN, end, low, high, tone.fill, tone.stroke, label, tone.ink, true);
      } else {
        box(start, leg.t, leg.low, leg.high, tone.fill, tone.stroke, `${legLabel} · ${label}`, tone.ink);
      }
    } else if (type === 'flat_top_breakout') {
      box(leg.t, end, low ?? high, high, tone.fill, tone.stroke, `BASE · ${label}`, tone.ink, true);
    } else if (type === 'red_to_green') {
      box(leg.t, end, low ?? leg.low, leg.high, tone.fill, tone.stroke, `RED${leg.bars ? ` ${leg.bars}` : ''} · ${label}`,
        tone.ink, true);
    }
  }
  return boxes;
}
