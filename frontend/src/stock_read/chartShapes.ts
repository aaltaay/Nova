/**
 * What each chart pane draws for the stock read (ADR 036). Pure: the read, the operator's layers and
 * a focus go in; a scene for the primitive and price lines for the series come out. Times are epoch
 * seconds until `toTime` maps them onto the pane's own bars.
 *
 * The 1-minute pane draws everything: each followed setup's shapes (the lead lane in colour, the rest
 * faded), the day's setups that ended under them (`pastShapes.ts`), the plan's risk and reward zones and
 * lines, the trade's levels (`levelPicks.minuteScene`: the high of day, the nearest top and bottom its
 * candles made, the nearest round number each side and the plan's levels between its stop and target),
 * and the moment's pin (ADR 037).
 * The 5-minute pane carries its own level map and the 5-minute setups (`fiveMinuteShapes.ts`; on the
 * 1-minute pane a 5-minute setup in reach is a dashed trigger line); the 5-minute and 10-second panes
 * mirror the plan's levels as thin lines. While you hold the stock (`read.held`), the trade's levels --
 * THEN, NEXT, SUPPORT, STOP, the average and the rounds broken or traded through -- are the 10-second
 * pane's, with their names (operator, 2026-10-01: "lets move these targets ... to the 10 seconds chart");
 * no other pane draws the plan's lines or zones then. The Full Day pane carries the daily level map (`levelPicks.ts`). A plan's
 * level is dashed while it is only a plan and solid while an order stands behind it. Nothing here is
 * estimated: every price is the scanner's, the read's or Nova's order's own.
 * A setup plan on a stock too thin to trade (2026-10-01) draws no plan: no zones, no plan-only lines, its
 * lane faded like the others -- an order that stands behind a level is still drawn.
 */
import type { Time } from 'lightweight-charts';
import { LEVEL_COLORS, SETUP_COLORS } from './constants';
import { heldLines } from './heldView';
import { levelScene, minuteScene } from './levelPicks';
import type { CallTone, MomentCall } from './momentModel';
import { drawnPast, failingNow, type Episode } from './pastSetups';
import { fiveMinuteOnMinute, fiveMinuteScene } from './fiveMinuteShapes';
import { laneHoverId, laneOnMinute, levelsOf } from './laneShapes';
import { pastRings, pastShapes } from './pastShapes';
import { formingProgress, fmtPx, setupName } from './planMath';
import { thinPlan } from './planVerdict';
import type { Scene, SceneBox, SceneDot, SceneMark, SceneWord } from './sceneTypes';
import type { StockReadLayers } from './StockReadContext';
import type { SetupLane, SetupLeg, StockPlan, StockRead } from './types';
import { levelTitle, type OrderLevel, type OrderLevels } from './whoTradesModel';

export { laneHoverId };

/** `full` the 1-minute, `map` the 5-minute, `thin` the 10-second, `daily` the Full Day chart. */
export type PaneKind = 'full' | 'map' | 'thin' | 'daily' | 'none';

export interface PriceLineSpec {
  id: string;
  price: number;
  color: string;
  width: 1 | 2;
  style: 'solid' | 'dashed' | 'dotted';
  title: string;
  axisLabel: boolean;
}

export interface PaneDraw {
  scene: Scene;
  lines: PriceLineSpec[];
}

export interface DrawOptions {
  pane: PaneKind;
  layers: StockReadLayers;
  /** Epoch seconds -> the pane's nearest bar time; null when the pane has no bars. */
  toTime: (epochSec: number) => Time | null;
  /** Where a leg began, from the pane's candles (the lowest low before its high). */
  legStart?: (leg: SetupLeg) => number;
  /** The high of the pane's candle that starts at an epoch second (a flat top's break). */
  highAt?: (epochSec: number) => number | null;
  focus?: { ts: number; title: string; setup: { trigger: number; stop: number; target1: number; armed_bar_t?: number } | null } | null;
  /** The levels with what stands behind each (Who trades, ADR 037); without them the plan's own, dashed. */
  levels?: OrderLevels | null;
  /** The moment's call: its pin goes on its candle. */
  call?: MomentCall | null;
  /** The day's setups that ended (ADR 036 amendment): drawn faint under the live lanes. */
  past?: Episode[] | null;
  /** The day's 5-minute setups that ended (`?tf=5m`): the 5-minute pane draws them. */
  past5?: Episode[] | null;
}

export const CALL_COLORS: Record<CallTone, string> = {
  go: '#30d158',
  target: '#ff9f0a',
  stop: '#ff453a',
  nova: '#0a84ff',
  done: '#30d158',
  wait: '#8e8e93',
  info: '#8e8e93',
};

const MIN = 60;

export function paneKind(timeframe: string): PaneKind {
  if (timeframe === '1Min') return 'full';
  if (timeframe === '5Min') return 'map';
  if (timeframe === '10Sec') return 'thin';
  if (timeframe === '1Day') return 'daily';
  return 'none';
}

/** A lane's rings, marks and edge words (the flat top's) into the pane's scene. */
function mergeExtras(scene: Scene, s: { dots?: SceneDot[]; marks?: SceneMark[]; words?: SceneWord[] }): void {
  if (s.dots?.length) scene.dots = [...(scene.dots ?? []), ...s.dots];
  if (s.marks?.length) scene.marks = [...(scene.marks ?? []), ...s.marks];
  if (s.words?.length) scene.words = [...(scene.words ?? []), ...s.words];
}

/** The plan's zones, from the consolidation's last bar to the pane's right edge. */
function planZones(lv: OrderLevels, startSec: number | null, o: DrawOptions): SceneBox[] {
  const entry = lv.entry?.price ?? null;
  const stop = lv.stop?.price ?? null;
  const target = lv.target?.price ?? null;
  if (entry === null || stop === null || target === null || startSec === null) return [];
  const t1 = o.toTime(startSec);
  if (t1 === null) return [];
  return [
    { t1, t2: null, p1: stop, p2: entry, fill: SETUP_COLORS.risk, stroke: SETUP_COLORS.stop,
      dashed: lv.stop?.behind === 'plan', label: null, labelColor: SETUP_COLORS.stop },
    { t1, t2: null, p1: entry, p2: target, fill: SETUP_COLORS.reward, stroke: SETUP_COLORS.target,
      dashed: lv.target?.behind === 'plan', label: null, labelColor: SETUP_COLORS.target },
  ];
}

function planOnly(price: number | null): OrderLevel | null {
  return price === null ? null : { price, behind: 'plan' };
}

/** The levels a pane draws: the ones Who trades knows what stands behind, else the plan's own -- none for a
 * setup plan too thin to trade (2026-10-01). */
export function drawnLevels(plan: StockPlan | null, levels: OrderLevels | null | undefined): OrderLevels | null {
  if (levels) return levels;
  if (!plan || thinPlan(plan)) return null;
  return { entry: planOnly(plan.entry), stop: planOnly(plan.stop), target: planOnly(plan.target) };
}

function planLines(plan: StockPlan | null, lv: OrderLevels, pane: PaneKind): PriceLineSpec[] {
  const out: PriceLineSpec[] = [];
  const thin = pane !== 'full';
  const r = plan?.rr == null ? '' : ` ${plan.rr.toFixed(plan.rr % 1 ? 1 : 0)}R`;
  const add = (id: 'entry' | 'stop' | 'target', level: OrderLevel | null, color: string) => {
    if (!level) return;
    const provisional = id === 'entry' && level.behind === 'plan' && plan?.provisional && plan.source === 'setup';
    out.push({
      id,
      price: level.price,
      color,
      width: thin ? 1 : 2,
      style: level.behind === 'plan' ? 'dashed' : 'solid',
      title: thin ? '' : provisional ? 'ENTRY (provisional)' : levelTitle(id, level.behind, r),
      axisLabel: !thin,
    });
  };
  add('entry', lv.entry, SETUP_COLORS.trigger);
  add('stop', lv.stop, SETUP_COLORS.stop);
  add('target', lv.target, SETUP_COLORS.target);
  return out;
}


/** Where a lane's drawing begins: the pole's first candle, the leg's low, the impulse, the open. */
export function laneStartSec(lane: SetupLane, legStart?: (leg: SetupLeg) => number): number | null {
  const leg = lane.leg;
  if (!leg) return lane.setup?.leg_t ?? null;
  if (lane.setup_type === 'bull_flag' && leg.bars) return leg.t - (leg.bars - 1) * MIN;
  if (lane.setup_type === 'first_pullback') return legStart?.(leg) ?? leg.t - 5 * MIN;
  return leg.t;
}

/** The lane the plan follows, if the plan is a setup's. */
export function leadLane(read: StockRead): SetupLane | null {
  const p = read.plan;
  if (!p || p.source !== 'setup') return null;
  return read.setups.find(l => l.setup_type === p.setup_type) ?? null;
}

export function paneDraw(read: StockRead | null, o: DrawOptions): PaneDraw {
  const empty: PaneDraw = {
    scene: { boxes: [], segments: [], vlines: [], edgeTags: [], pins: [], keepInView: null, labels: o.layers.labels },
    lines: [],
  };
  if (!read || o.pane === 'none') return empty;
  if (o.pane === 'daily') {
    // The Full Day pane: the daily level map alone.
    if (!o.layers.levels) return empty;
    const d = levelScene(read, 'daily');
    return { scene: { ...empty.scene, levels: d.levels, ticks: d.ticks, edgeTags: d.tags }, lines: [] };
  }
  const plan = read.plan;
  const lead = leadLane(read);
  const scene: Scene = {
    boxes: [], segments: [], vlines: [], edgeTags: [], pins: [], keepInView: null, labels: o.layers.labels,
  };
  const lines: PriceLineSpec[] = [];
  const held = read.held;
  const lv = held ? null : drawnLevels(plan, o.levels);
  if (o.layers.setups) {
    if (held && o.pane === 'thin') lines.push(...heldLines(held));
    if (lv) lines.push(...planLines(plan, lv, o.pane));
    if (o.pane === 'full') {
      // The day's setups that ended go under the live lanes; a lane failed right now is drawn as past.
      const past = o.layers.past && o.past ? o.past : [];
      const failing = failingNow(past);
      const drawn = drawnPast(past, o.layers.hidden);
      scene.boxes.push(...pastShapes(drawn, o));
      mergeExtras(scene, { dots: pastRings(drawn, o) });
      for (const lane of read.setups) {
        if (o.layers.hidden.includes(lane.setup_type)) continue;
        if (lane.state === 'failed' && failing.has(lane.setup_type)) continue;
        const s = laneOnMinute(lane, lane === lead && !thinPlan(plan), o);
        scene.boxes.push(...s.boxes);
        scene.segments.push(...s.segments);
        mergeExtras(scene, s);
      }
      if (lv && (!lead || !o.layers.hidden.includes(lead.setup_type))) {
        const shape = lead ? levelsOf(lead) : null;
        const start = shape?.end ?? lead?.series?.bars_as_of ?? read.setups.find(l => l.series)?.series?.bars_as_of
          ?? (read.generated_at ? Math.floor(read.generated_at / MIN) * MIN - MIN : null);
        scene.boxes.push(...planZones(lv, start, o));
        if (lv.stop && lv.target) scene.keepInView = { min: lv.stop.price, max: lv.target.price };
      }
      // A 5-minute setup armed or near its trigger: one dashed line here (the chip is the legend's).
      lines.push(...fiveMinuteOnMinute(read).lines);
    } else if (o.pane === 'map') {
      // The 5-minute setups: drawn on this pane only (operator decision 2026-09-30).
      const f = fiveMinuteScene(read, { toTime: o.toTime, legStart: o.legStart, highAt: o.highAt,
        hidden: o.layers.hidden, past: o.layers.past ? o.past5 ?? null : null });
      scene.boxes.push(...f.boxes);
      scene.segments.push(...f.segments);
      mergeExtras(scene, f);
      lines.push(...f.lines);
    }
  }
  const pin = o.pane === 'full' ? o.call?.pin ?? null : null;
  if (pin && o.call) {
    const t = o.toTime(pin.at ?? read.generated_at);
    if (t !== null) scene.pins.push({ t, price: pin.price, label: pin.label, color: CALL_COLORS[o.call.tone] });
  }
  if (o.layers.levels && o.pane === 'map') {
    const m = levelScene(read, 'map');
    scene.levels = m.levels;
    scene.ticks = m.ticks;
    scene.edgeTags.push(...m.tags);
  } else if (o.layers.levels && o.pane === 'full') {
    // Drawn by the scene like the 5-minute pane's, so each says what it is and opens its card: a price
    // line shows its title only beside an axis label (lightweight-charts 5.1), and these had none.
    const m = minuteScene(read);
    scene.levels = m.levels;
    scene.edgeTags.push(...m.tags);
    // The chart's own VWAP line draws it in view (the same VWAP since it restarts at 16:00); out of view
    // it gets a tag -- the line's own tag when the chart shows VWAP (one id: the edge column keeps one).
    const vwap = read.levels.vwap;
    if (vwap !== null) {
      scene.edgeTags.push({ price: vwap, label: `VWAP ${fmtPx(vwap)}`, color: LEVEL_COLORS.vwap, id: 'vwap' });
    }
  }
  if (o.pane === 'full' && o.focus) {
    const t = o.toTime(o.focus.ts);
    if (t !== null) scene.vlines.push({ t, color: '#ffd60a', label: o.focus.title });
    const s = o.focus.setup;
    const armed = s?.armed_bar_t ?? o.focus.ts;
    const t1 = o.toTime(armed);
    if (s && t1 !== null) {
      scene.segments.push(
        { t1, price: s.trigger, color: SETUP_COLORS.trigger, dashed: true, label: `then: trigger ${fmtPx(s.trigger)}` },
        { t1, price: s.stop, color: SETUP_COLORS.stop, dashed: true, label: `stop ${fmtPx(s.stop)}` },
        { t1, price: s.target1, color: SETUP_COLORS.target, dashed: true, label: `target ${fmtPx(s.target1)}` },
      );
    }
  }
  return { scene, lines };
}

/** The legend chip for a lane: its short name and where it stands. */
export function laneChip(lane: SetupLane): { text: string; state: 'forming' | 'live' | 'done' | 'idle' | 'failed' } {
  const short: Record<string, string> = {
    first_pullback: '1st pullback', bull_flag: 'Bull flag', flat_top_breakout: 'Flat top', flat_top_5m: '5m flat top',
    red_to_green: 'Red→green', gap_and_go: 'Gap & Go',
  };
  const name = short[lane.setup_type] ?? setupName(lane.setup_type);
  const prog = formingProgress(lane);
  if (lane.state === 'triggered') return { text: `${name} triggered`, state: 'done' };
  if (lane.state === 'armed' || lane.state === 'near') return { text: `${name} ${lane.state}`, state: 'live' };
  if (lane.state === 'failed') return { text: `${name} failed`, state: 'failed' };
  if (lane.state === 'leg' || lane.state === 'pullback' || lane.forming) {
    return { text: prog ? `${name} ${prog}` : `${name} forming`, state: 'forming' };
  }
  if (lane.window?.state === 'after') return { text: `${name} closed`, state: 'idle' };
  return { text: name, state: 'idle' };
}

/** "BULL FLAG · FORMING 1 OF 2" for the pane's corner. */
export function planBadgeText(read: StockRead): string | null {
  const p = read.plan;
  if (!p) return null;
  if (p.source === 'manual') return 'YOUR PLAN';
  const lane = leadLane(read);
  const prog = formingProgress(lane);
  const state = p.state === 'forming' && prog ? `FORMING ${prog.replace('/', ' OF ')}` : p.state.toUpperCase();
  return `${setupName(p.setup_type).toUpperCase()} · ${state}`;
}
