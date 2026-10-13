/**
 * A setup's plan on the 1-minute chart is one box from its stop to target 1, never zones and lines across the pane.
 * Forming (operator ask 2026-10-12, on MNDR's Gap and Go plan at 09:01 with the entry 30% over the price: "square it up
 * like the original but show it more faded ... say gap and go strategy, but doesn't have to be entire horizontal line
 * from end to end ... more minimalist"): one faint box, standing on the setup's window while that is ahead. Near or
 * armed (operator ask the same day, on that plan once armed: "its making the chart extremely big ... can we do that for
 * the rest of them?"): the same box in full colour right of the newest candle, saying where the setup stands, its
 * prices on the axis. Neither stretches the frame to target 2. Triggered (operator ask the same day, option A of the
 * mockups): with nothing behind it the trade was taken or missed, so the plan leaves the chart -- no box, no axis tags,
 * no frame -- and a mark over its trigger candle says when. A level an order or a position stands behind, and the
 * operator's own plan, still draw the zones and lines. The 10-second chart draws the same box on its own candles
 * (operator choice 2026-10-13, of three mockups, after AIXI's Gap and Go drew four unnamed lines there: "for which
 * strategy is this specifically?"), so the strategy is named on both. Pure: which plans are boxed, the scene's box
 * (`SceneStrategy`), its edge-column words and the triggered plan's mark; `strategyBoxRender.ts` places and draws the
 * box on the pane.
 */
import type { Time } from 'lightweight-charts';
import { EDGE_PRIORITY } from '../chart';
import { etChartSeconds } from '../tickerChartData';
import { SETUP_COLORS, STRATEGY_BOX, STRATEGY_BOX_LIVE } from './constants';
import { fmtPx, setupName } from './planMath';
import type { SceneMark, SceneStrategy, SceneWord } from './sceneTypes';
import { hhmmEt } from './timeWords';
import type { SetupLevels, StockPlan } from './types';
import type { OrderLevels } from './whoTradesModel';

const DAY_SEC = 86_400;
const MIN = 60;
/** The triggered plan's mark places its label before any other's. */
const TRIGGER_MARK_RANK = Number.MAX_SAFE_INTEGER;

/** A setup's plan with nothing but the plan behind its levels. An order or a position makes it real. */
function planOnly(plan: StockPlan | null, lv: OrderLevels): plan is StockPlan {
  if (!plan || plan.source !== 'setup' || plan.state === 'manual') return false;
  return [lv.entry, lv.stop, lv.target, lv.target2].every(l => !l || l.behind === 'plan');
}

/** Such a plan while its setup is forming, near or armed: its box. */
export function boxedPlan(plan: StockPlan | null, lv: OrderLevels): boolean {
  return planOnly(plan, lv) && plan.state !== 'triggered';
}

/** Such a plan once its setup triggered: taken or missed, it leaves the 1-minute chart, its mark in its place. */
export function triggeredPlan(plan: StockPlan | null, lv: OrderLevels): boolean {
  return planOnly(plan, lv) && plan.state === 'triggered';
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

/** "GAP AND GO", "FAILED BREAKOUT ▼ SHORT". */
function planName(plan: StockPlan): string {
  return `${setupName(plan.setup_type).toUpperCase()}${plan.side === 'short' ? ' ▼ SHORT' : ''}`;
}

/** The plan's box, its window counted in candles from the newest one (`afterSec`, mapped to `after`); `setup` is the
 * lead lane's levels, which say when it armed. A triggered plan has none (`triggeredPlan`). */
export function strategyOf(plan: StockPlan, lv: OrderLevels, target2: number | null, after: Time,
  afterSec: number, setup: SetupLevels | null = null): SceneStrategy | null {
  if (plan.state === 'triggered') return null;
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
  const name = planName(plan);
  const side = short ? 'short' : 'long';
  if (state !== 'forming') {
    // Near or armed: after the newest candle to the edge, saying since when it armed and, while its window is open,
    // until when.
    const at = setup?.armed_at;
    const said = [...(at ? [`since ${hhmmEt(at)}`] : []), ...(open && w ? [`until ${w.end}`] : [])].join(' · ');
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

/** The box counted on a pane of shorter candles (the 10-second): after that pane's newest candle `last` (`sec` on the
 * chart's clock, ET read as UTC), its window in that pane's candles of `barSec` seconds. `fromSec` is the epoch second
 * of the 1-minute candle `strategyOf` counted its window from. */
export function strategyOnBars(s: SceneStrategy, fromSec: number, last: { t: Time; sec: number },
  barSec: number): SceneStrategy {
  const from = etChartSeconds(fromSec * 1000);
  const bars = (minutes: number | null) => (minutes === null ? null : Math.round((from + minutes * MIN - last.sec) / barSec));
  return { ...s, after: last.t, startBars: bars(s.startBars), endBars: bars(s.endBars) };
}

/** The box's edge-column words, beside its edges, its entry line and target 2's dash, with no line of their own.
 * Forming: faint, with the prices ("T1 2.99"). Once armed the axis carries the prices, so the words only name them
 * ("T1", "entry"), and out of view their tags add the price. Each takes the name of a level at its price
 * ("stop 4.03 · $4.00", `levelFold.ts`; operator report 2026-10-13); target 2's is the column's word too, so a
 * level at it folds in as at the others. */
export function strategyWords(s: SceneStrategy): SceneWord[] {
  const live = s.state !== 'forming';
  const ink = live ? STRATEGY_BOX_LIVE : STRATEGY_BOX;
  const word = (id: string, label: string, price: number, color: string): SceneWord => ({
    id: `strategy:${id}`, text: live ? label : `${label} ${fmtPx(price)}`, color, priority: EDGE_PRIORITY.planLine,
    price, series: null, valueWhenOff: live, style: 'plain', absorbs: true,
  });
  return [
    ...(s.target2 !== null ? [word('target2', 'T2', s.target2, ink.target2Ink)] : []),
    word('target', 'T1', s.target, ink.targetInk),
    word('entry', s.side === 'short' ? 'short' : 'entry', s.entry, ink.entryInk),
    word('stop', 'stop', s.stop, ink.stopInk),
  ];
}

/** A triggered plan's mark (`triggeredPlan`): over its trigger candle, pointing the way it trades, "✓ GAP AND GO 09:31"
 * -- a ✓ alone while the labels are compact, its hover (`hoverId`, the lane's) the rest. Null without the lane's
 * trigger time, or with its candle off the pane's bars. */
export function triggerMark(plan: StockPlan, setup: SetupLevels | null,
  o: { toTime: (epochSec: number) => Time | null; highAt?: (epochSec: number) => number | null },
  hoverId: string): SceneMark | null {
  if (!setup?.triggered_at) return null;
  const bar = Math.floor(setup.triggered_at / MIN) * MIN;
  const t = o.toTime(bar);
  if (t === null) return null;
  const when = hhmmEt(setup.triggered_at);
  return {
    t, price: o.highAt?.(bar) ?? setup.trigger, color: SETUP_COLORS.trigger, rank: TRIGGER_MARK_RANK,
    dir: plan.side === 'short' ? 'down' : 'up', label: `✓ ${planName(plan)} ${when}`,
    shrink: { short: `✓ ${when}`, icon: '✓', rank: TRIGGER_MARK_RANK }, hoverId,
  };
}
