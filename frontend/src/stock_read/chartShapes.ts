/**
 * What each chart pane draws for the stock read (ADR 036). Pure: the read, the operator's layers and
 * a focus go in; a scene for the primitive and price lines for the series come out. Times are epoch
 * seconds until `toTime` maps them onto the pane's own bars.
 *
 * The 1-minute pane draws everything: each followed setup's shapes (the lead lane in colour, the rest
 * faded), the plan's risk and reward zones and lines, the day's levels. The 5-minute and 10-second
 * panes mirror the plan's levels and the high of day as thin lines. Nothing here is estimated: every
 * price is the scanner's or the read's own.
 */
import type { Time } from 'lightweight-charts';
import { SETUP_COLORS } from './constants';
import { formingProgress, fmtPx, setupName } from './planMath';
import type { Scene, SceneBox, SceneSegment } from './SetupShapesPrimitive';
import type { StockReadLayers } from './StockReadContext';
import type { SetupLane, SetupLeg, StockPlan, StockRead } from './types';

export type PaneKind = 'full' | 'thin' | 'none';

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
  focus?: { ts: number; title: string; setup: { trigger: number; stop: number; target1: number; armed_bar_t?: number } | null } | null;
}

const MIN = 60;
const LIVE_DRAWN = new Set(['leg', 'pullback', 'armed', 'near', 'triggered', 'filtered', 'failed']);

export function paneKind(timeframe: string): PaneKind {
  if (timeframe === '1Min') return 'full';
  if (timeframe === '5Min' || timeframe === '10Sec') return 'thin';
  return 'none';
}

function tone(state: StockPlan['state'] | string): { stroke: string; fill: string } {
  if (state === 'triggered') return { stroke: SETUP_COLORS.target, fill: 'rgba(48, 209, 88, 0.12)' };
  if (state === 'armed' || state === 'near' || state === 'manual') return { stroke: SETUP_COLORS.trigger, fill: SETUP_COLORS.leg };
  return { stroke: SETUP_COLORS.formingStroke, fill: SETUP_COLORS.forming };
}

function pct(x: number): string {
  return `${x >= 0 ? '+' : ''}${(x * 100).toFixed(1)}%`;
}

/** The lane's drawable levels: an armed setup's, else what a forming one would arm with. */
function levelsOf(lane: SetupLane): { trigger: number; stop: number; bars: number; end: number | null } | null {
  if (lane.setup && lane.state !== 'watching') {
    return { trigger: lane.setup.trigger, stop: lane.setup.stop, bars: lane.setup.pullback_bars ?? 0,
      end: lane.setup.armed_bar_t ?? null };
  }
  if (lane.forming) return { trigger: lane.forming.trigger, stop: lane.forming.stop, bars: lane.forming.bars, end: null };
  return null;
}

function laneShapes(lane: SetupLane, lead: boolean, o: DrawOptions): { boxes: SceneBox[]; segments: SceneSegment[] } {
  const boxes: SceneBox[] = [];
  const segments: SceneSegment[] = [];
  const leg = lane.leg;
  if (!LIVE_DRAWN.has(lane.state) && !lane.forming) return { boxes, segments };
  // A failed setup stays on the chart faded for as long as the scanner shows it, saying so.
  const failed = lane.state === 'failed';
  const bright = lead && !failed;
  const c = bright ? tone(lane.state === 'leg' || lane.state === 'pullback' ? 'forming' : lane.state)
    : { stroke: SETUP_COLORS.fadedStroke, fill: SETUP_COLORS.faded };
  const legFill = bright ? SETUP_COLORS.leg : SETUP_COLORS.faded;
  const legStroke = bright ? SETUP_COLORS.legStroke : SETUP_COLORS.fadedStroke;
  const tag = failed ? ' · FAILED' : '';
  const lv = levelsOf(lane);
  const lastT = lane.series?.bars_as_of ?? null;
  const endT = lv?.end ?? lastT;
  const box = (t1s: number, t2s: number, p1: number, p2: number, fill: string, stroke: string, labelText: string,
    dashed = false, labelBelow = false) => {
    const t1 = o.toTime(t1s);
    const t2 = o.toTime(t2s);
    if (t1 === null || t2 === null) return;
    boxes.push({ t1, t2, p1, p2, fill, stroke, dashed, label: labelText, labelColor: stroke, labelBelow });
  };
  const type = lane.setup_type;
  const provisional = !lane.setup;
  if (type === 'first_pullback' || type === 'bull_flag') {
    if (leg) {
      const start = type === 'bull_flag' && leg.bars ? leg.t - (leg.bars - 1) * MIN : (o.legStart?.(leg) ?? leg.t - 5 * MIN);
      box(start, leg.t, leg.low, leg.high, legFill, legStroke, `${type === 'bull_flag' ? 'POLE' : 'LEG'} ${pct(leg.pct)}`);
    }
    if (lv && leg && endT !== null && endT > leg.t) {
      const prog = type === 'bull_flag' ? formingProgress(lane) : null;
      const n = lv.bars ? ` ${lv.bars}` : '';
      box(leg.t + MIN, endT, lv.stop, lv.trigger, c.fill, c.stroke,
        `${type === 'bull_flag' ? `FLAG${prog ? ` ${prog}` : n}` : `PULLBACK${n}`}${tag}`, provisional, true);
    }
  } else if (type === 'flat_top_breakout') {
    if (lv && leg && endT !== null) {
      box(leg.t, endT, lv.stop, lv.trigger, c.fill, c.stroke, `BASE${lv.bars ? ` ${lv.bars}` : ''}${tag}`, provisional, true);
      const t1 = o.toTime(leg.t);
      if (t1 !== null) segments.push({ t1, price: lv.trigger, color: c.stroke, dashed: true, label: `FLAT TOP ${fmtPx(lv.trigger)}` });
    }
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
  }
  return { boxes, segments };
}

/** The plan's zones, from the consolidation's last bar to the pane's right edge. */
function planZones(plan: StockPlan, startSec: number | null, o: DrawOptions): SceneBox[] {
  if (plan.entry === null || plan.stop === null || plan.target === null || startSec === null) return [];
  const t1 = o.toTime(startSec);
  if (t1 === null) return [];
  return [
    { t1, t2: null, p1: plan.stop, p2: plan.entry, fill: SETUP_COLORS.risk, stroke: SETUP_COLORS.stop,
      dashed: true, label: null, labelColor: SETUP_COLORS.stop },
    { t1, t2: null, p1: plan.entry, p2: plan.target, fill: SETUP_COLORS.reward, stroke: SETUP_COLORS.target,
      dashed: true, label: null, labelColor: SETUP_COLORS.target },
  ];
}

function planLines(plan: StockPlan, pane: PaneKind): PriceLineSpec[] {
  const out: PriceLineSpec[] = [];
  const thin = pane === 'thin';
  const dashed = plan.provisional || thin;
  const r = plan.rr === null ? '' : ` ${plan.rr.toFixed(plan.rr % 1 ? 1 : 0)}R`;
  const add = (id: string, price: number | null, color: string, title: string) => {
    if (price === null) return;
    out.push({ id, price, color, width: thin ? 1 : 2, style: dashed ? 'dashed' : 'solid', title: thin ? '' : title,
      axisLabel: !thin });
  };
  add('entry', plan.entry, SETUP_COLORS.trigger, plan.provisional && plan.source === 'setup' ? 'ENTRY (provisional)' : 'ENTRY');
  add('stop', plan.stop, SETUP_COLORS.stop, 'STOP');
  add('target', plan.target, SETUP_COLORS.target, `TARGET${r}`);
  return out;
}

function levelLines(read: StockRead, pane: PaneKind): { lines: PriceLineSpec[]; tags: Scene['edgeTags'] } {
  const lv = read.levels;
  const lines: PriceLineSpec[] = [];
  const tags: Scene['edgeTags'] = [];
  const add = (id: string, price: number | null, title: string, color: string, tag?: string) => {
    if (price === null) return;
    lines.push({ id, price, color, width: 1, style: 'dotted', title: pane === 'full' ? title : '', axisLabel: false });
    tags.push({ price, label: tag ?? `${title} ${fmtPx(price)}`, color });
  };
  add('hod', lv.hod?.price ?? null, 'HOD', SETUP_COLORS.level);
  if (pane === 'full') {
    add('pmh', lv.pmh, 'PMH', SETUP_COLORS.level);
    add('open', lv.open, 'Open', SETUP_COLORS.level);
    for (const [id, price] of [['round_above', lv.round_above], ['round_below', lv.round_below]] as const) {
      if (price !== null) add(id, price, `$${fmtPx(price)}`, SETUP_COLORS.round, `$${fmtPx(price)}`);
    }
    // The chart's own VWAP line draws it in view; out of view it gets a tag.
    if (lv.vwap !== null) tags.push({ price: lv.vwap, label: `VWAP ${fmtPx(lv.vwap)}`, color: '#bf5af2' });
  }
  return { lines, tags };
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
  const empty: PaneDraw = { scene: { boxes: [], segments: [], vlines: [], edgeTags: [], keepInView: null }, lines: [] };
  if (!read || o.pane === 'none') return empty;
  const plan = read.plan;
  const lead = leadLane(read);
  const scene: Scene = { boxes: [], segments: [], vlines: [], edgeTags: [], keepInView: null };
  const lines: PriceLineSpec[] = [];
  if (o.layers.setups) {
    if (plan) lines.push(...planLines(plan, o.pane));
    if (o.pane === 'full') {
      for (const lane of read.setups) {
        if (o.layers.hidden.includes(lane.setup_type)) continue;
        const s = laneShapes(lane, lane === lead, o);
        scene.boxes.push(...s.boxes);
        scene.segments.push(...s.segments);
      }
      if (plan && (!lead || !o.layers.hidden.includes(lead.setup_type))) {
        const lv = lead ? levelsOf(lead) : null;
        const start = lv?.end ?? lead?.series?.bars_as_of ?? read.setups.find(l => l.series)?.series?.bars_as_of
          ?? (read.generated_at ? Math.floor(read.generated_at / MIN) * MIN - MIN : null);
        scene.boxes.push(...planZones(plan, start, o));
        if (plan.stop !== null && plan.target !== null) scene.keepInView = { min: plan.stop, max: plan.target };
      }
    }
  }
  if (o.layers.levels) {
    const lv = levelLines(read, o.pane);
    lines.push(...lv.lines);
    scene.edgeTags.push(...lv.tags);
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
    first_pullback: '1st pullback', bull_flag: 'Bull flag', flat_top_breakout: 'Flat top', red_to_green: 'Red→green',
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
