/**
 * A forming setup's plan on the 1-minute chart (operator ask 2026-10-12, on MNDR's Gap and Go plan at 09:01 with the
 * entry 30% over the price: "square it up like the original but show it more faded ... say gap and go strategy, but
 * doesn't have to be entire horizontal line from end to end ... more minimalist"). A plan the setup has not armed is
 * one faint box from its stop to target 1, standing on the setup's window while that is ahead: never the zones and
 * full-width lines of a trade that can be taken, and never a frame stretched to target 2. Pure: which plans are only
 * forming, the scene's box (`SceneStrategy`) and its prices as the edge column's words; `strategyBoxRender.ts` places
 * and draws the box on the pane.
 */
import type { Time } from 'lightweight-charts';
import { EDGE_PRIORITY } from '../chart';
import { etChartSeconds } from '../tickerChartData';
import { STRATEGY_BOX } from './constants';
import { fmtPx, setupName } from './planMath';
import type { SceneStrategy, SceneWord } from './sceneTypes';
import type { StockPlan } from './types';
import type { OrderLevels } from './whoTradesModel';

const DAY_SEC = 86_400;

/** A setup's plan that is only forming: no setup armed it, and nothing but the plan stands behind its levels. */
export function formingPlan(plan: StockPlan | null, lv: OrderLevels): boolean {
  if (!plan || plan.source !== 'setup' || plan.state !== 'forming') return false;
  return [lv.entry, lv.stop, lv.target, lv.target2].every(l => !l || l.behind === 'plan');
}

/** "09:30" -> minutes into the day; null for anything else. */
function minutesOf(hhmm: string): number | null {
  const m = /^(\d{1,2}):(\d{2})$/.exec(hhmm);
  return m ? Number(m[1]) * 60 + Number(m[2]) : null;
}

/** Minutes into the Eastern day of an epoch second. */
function etMinuteOfDay(epochSec: number): number {
  const s = etChartSeconds(epochSec * 1000);
  return Math.floor((((s % DAY_SEC) + DAY_SEC) % DAY_SEC) / 60);
}

/** The forming plan's box, its window counted in candles from the newest one (`afterSec`, mapped to `after`). */
export function strategyOf(plan: StockPlan, lv: OrderLevels, target2: number | null, after: Time,
  afterSec: number): SceneStrategy | null {
  const entry = lv.entry?.price ?? null;
  const stop = lv.stop?.price ?? null;
  const target = lv.target?.price ?? null;
  if (entry === null || stop === null || target === null) return null;
  const short = plan.side === 'short';
  const w = plan.window;
  const from = w ? minutesOf(w.start) : null;
  const to = w ? minutesOf(w.end) : null;
  const now = etMinuteOfDay(afterSec);
  const ahead = w?.state === 'before' && from !== null && from > now;
  const open = w?.state === 'open' && to !== null;
  let when = '';
  let whenWaiting = '';
  if (ahead && w) {
    when = to !== null ? `${w.start}–${w.end}` : `from ${w.start}`;
    whenWaiting = `from ${w.start} →`;
  } else if (open && w) {
    when = `until ${w.end}`;
    whenWaiting = when;
  }
  return {
    after,
    startBars: ahead && from !== null ? from - now : null,
    endBars: (ahead || open) && to !== null ? to - now : null,
    entry, stop, target, target2,
    side: short ? 'short' : 'long',
    name: `${setupName(plan.setup_type).toUpperCase()}${short ? ' ▼ SHORT' : ''}`,
    word: 'strategy',
    when, whenWaiting,
  };
}

/** The box's prices as the edge column's words, beside its edges and its entry line: faint, with no line of their own. */
export function strategyWords(s: SceneStrategy): SceneWord[] {
  const word = (id: string, text: string, price: number, color: string): SceneWord => ({
    id: `strategy:${id}`, text, color, priority: EDGE_PRIORITY.planLine, price, series: null, valueWhenOff: false,
    style: 'plain',
  });
  return [
    word('target', `T1 ${fmtPx(s.target)}`, s.target, STRATEGY_BOX.targetInk),
    word('entry', `${s.side === 'short' ? 'short' : 'entry'} ${fmtPx(s.entry)}`, s.entry, STRATEGY_BOX.entryInk),
    word('stop', `stop ${fmtPx(s.stop)}`, s.stop, STRATEGY_BOX.stopInk),
  ];
}
