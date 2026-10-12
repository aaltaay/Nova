/**
 * A setup's plan on the 1-minute chart is one box from its stop to target 1, never zones and lines across the pane.
 * Forming (operator ask 2026-10-12, on MNDR's Gap and Go plan at 09:01 with the entry 30% over the price: "square it up
 * like the original but show it more faded ... say gap and go strategy, but doesn't have to be entire horizontal line
 * from end to end ... more minimalist"): one faint box, standing on the setup's window while that is ahead. Near, armed
 * or triggered (operator ask the same day, on that plan once armed: "its making the chart extremely big ... can we do
 * that for the rest of them?"): the same box in full colour right of the newest candle, saying where the setup stands,
 * its prices on the axis. Neither stretches the frame to target 2. A level an order or a position stands behind, and
 * the operator's own plan, still draw the zones and lines. Pure: which plans are boxed, the scene's box
 * (`SceneStrategy`) and its edge-column words; `strategyBoxRender.ts` places and draws the box on the pane.
 */
import type { Time } from 'lightweight-charts';
import { EDGE_PRIORITY } from '../chart';
import { etChartSeconds } from '../tickerChartData';
import { STRATEGY_BOX, STRATEGY_BOX_LIVE } from './constants';
import { fmtPx, setupName } from './planMath';
import type { SceneStrategy, SceneWord } from './sceneTypes';
import { hhmmEt } from './timeWords';
import type { SetupLevels, StockPlan } from './types';
import type { OrderLevels } from './whoTradesModel';

const DAY_SEC = 86_400;

/** A setup's plan with nothing but the plan behind its levels: its box. An order or a position makes it real. */
export function boxedPlan(plan: StockPlan | null, lv: OrderLevels): boolean {
  if (!plan || plan.source !== 'setup' || plan.state === 'manual') return false;
  return [lv.entry, lv.stop, lv.target, lv.target2].every(l => !l || l.behind === 'plan');
}

/** A boxed plan no setup armed yet: the faint box. */
export function formingPlan(plan: StockPlan | null, lv: OrderLevels): boolean {
  return boxedPlan(plan, lv) && plan?.state === 'forming';
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

/** The plan's box, its window counted in candles from the newest one (`afterSec`, mapped to `after`); `setup` is the
 * lead lane's levels, which say when it armed and triggered. */
export function strategyOf(plan: StockPlan, lv: OrderLevels, target2: number | null, after: Time,
  afterSec: number, setup: SetupLevels | null = null): SceneStrategy | null {
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
  const state = plan.state === 'manual' ? 'forming' : plan.state;
  const name = `${setupName(plan.setup_type).toUpperCase()}${short ? ' ▼ SHORT' : ''}`;
  const side = short ? 'short' : 'long';
  if (state !== 'forming') {
    // Near, armed or triggered: after the newest candle to the edge, saying when it armed (or triggered) and, while it
    // can still trigger in an open window, until when.
    const triggered = state === 'triggered';
    const at = triggered ? setup?.triggered_at : setup?.armed_at;
    const said = [
      ...(at ? [`${triggered ? 'at' : 'since'} ${hhmmEt(at)}`] : []),
      ...(open && w && !triggered ? [`until ${w.end}`] : []),
    ].join(' · ');
    return { after, startBars: null, endBars: null, entry, stop, target, target2, side, state, name, word: state,
      when: said, whenWaiting: said };
  }
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
    entry, stop, target, target2, side, state, name,
    word: 'strategy',
    when, whenWaiting,
  };
}

/** The box's edge-column words, beside its edges and its entry line, with no line of their own. Forming: faint, with
 * the prices ("T1 2.99"). Once armed the axis carries the prices, so the words only name them ("T1", "entry"). */
export function strategyWords(s: SceneStrategy): SceneWord[] {
  const live = s.state !== 'forming';
  const ink = live ? STRATEGY_BOX_LIVE : STRATEGY_BOX;
  const word = (id: string, label: string, price: number, color: string): SceneWord => ({
    id: `strategy:${id}`, text: live ? label : `${label} ${fmtPx(price)}`, color, priority: EDGE_PRIORITY.planLine,
    price, series: null, valueWhenOff: false, style: 'plain',
  });
  return [
    word('target', 'T1', s.target, ink.targetInk),
    word('entry', s.side === 'short' ? 'short' : 'entry', s.entry, ink.entryInk),
    word('stop', 'stop', s.stop, ink.stopInk),
  ];
}
