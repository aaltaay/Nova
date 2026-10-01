/**
 * The 5-minute setups on the charts (operator decision 2026-09-30, on the mockup: "build it this way",
 * chart only, and on the 1-minute "a chip and its trigger line"). Pure.
 *
 * The built-in 5-minute lanes (`read.setups_5m`: the first pullback, the bull flag and the flat top read
 * on 5-minute candles) draw on the 5-minute pane the way the 1-minute pane draws its lanes -- the lead in
 * colour, the rest faded, the ones that ended faint with how they ended (`?tf=5m` past setups) -- every
 * label starting "5m", and the lead's trigger, stop and target as dashed lines. On the 1-minute pane a
 * 5-minute setup armed or near its trigger is a chip in the legend and one dashed line at its trigger;
 * nothing else of it. Their hover ids are their own (`lane5:`, `past5:`), so a card never mixes the two.
 */
import type { PriceLineSpec } from './chartShapes';
import { SETUP_COLORS } from './constants';
import { laneShapes, type LaneDrawOptions } from './laneShapes';
import { drawnPast, failingNow, type Episode } from './pastSetups';
import { pastHoverId, pastShapes } from './pastShapes';
import { fmtPx, setupName } from './planMath';
import type { SceneBox, SceneSegment } from './sceneTypes';
import type { SetupLane, StockRead } from './types';

export const FIVE_MIN_SEC = 300;
const PREFIX = '5m · ';
/** Where a 5-minute lane stands, most advanced first. */
const RANK: Record<string, number> = { near: 0, armed: 1, triggered: 2, pullback: 3, leg: 4 };
const IN_REACH = new Set(['armed', 'near']);
/** A faded lane's label makes room (`sceneLabels.ts`): whole where it fits, else none -- its box and hover
 * stay. Over the day's ended setups' labels, under nothing the lead or the levels say. */
const RANK_FADED_LANE = 2.5e10;
/** A setup's name on a chip: the words a trader says. */
const CHIP_NAMES: Record<string, string> = {
  first_pullback: 'first pullback', bull_flag: 'bull flag', flat_top_breakout: 'flat top',
};

export function lane5HoverId(setupType: string): string {
  return `lane5:${setupType}`;
}

export function past5HoverId(ep: Episode): string {
  return `past5:${ep.id}`;
}

/** The most advanced 5-minute lane: near, armed, triggered, then forming; null when none is. */
export function leadFive(lanes: SetupLane[]): SetupLane | null {
  const live = lanes.filter(l => l.state in RANK);
  live.sort((a, b) => RANK[a.state] - RANK[b.state]);
  return live[0] ?? null;
}

function named<T extends { label: string | null }>(x: T): T {
  return x.label ? { ...x, label: `${PREFIX}${x.label}` } : x;
}

export interface FiveMinuteDraw {
  boxes: SceneBox[];
  segments: SceneSegment[];
  lines: PriceLineSpec[];
}

export interface FiveMinuteOptions extends LaneDrawOptions {
  /** The setups the operator hid on the legend. */
  hidden: string[];
  /** The day's 5-minute setups that ended, when the Past layer is on. */
  past: Episode[] | null;
}

/** What the 5-minute pane draws of the 5-minute lanes. */
export function fiveMinuteScene(read: StockRead, o: FiveMinuteOptions): FiveMinuteDraw {
  const out: FiveMinuteDraw = { boxes: [], segments: [], lines: [] };
  const lanes = (read.setups_5m ?? []).filter(l => !o.hidden.includes(l.setup_type));
  const past = o.past ? drawnPast(o.past, o.hidden) : [];
  const failing = failingNow(past);
  for (const box of pastShapes(past, { toTime: o.toTime, legStart: o.legStart, barSec: FIVE_MIN_SEC })) {
    const ep = past.find(e => pastHoverId(e) === box.hoverId);
    out.boxes.push({
      ...named(box),
      shrink: box.shrink && box.shrink.short ? { ...box.shrink, short: `${PREFIX}${box.shrink.short}` } : box.shrink,
      hoverId: ep ? past5HoverId(ep) : box.hoverId,
    });
  }
  const lead = leadFive(lanes);
  for (const lane of lanes) {
    if (lane.state === 'failed' && failing.has(lane.setup_type)) continue;   // drawn as past instead
    const isLead = lane === lead;
    const s = laneShapes(lane, isLead, o, FIVE_MIN_SEC, lane5HoverId(lane.setup_type));
    out.boxes.push(...s.boxes.map(b => (isLead ? named(b)
      : { ...named(b), shrink: { short: null, icon: null, rank: RANK_FADED_LANE + (lane.leg?.t ?? 0) } })));
    out.segments.push(...s.segments.map(named));
  }
  const s = lead?.setup;
  if (lead && s && (IN_REACH.has(lead.state) || lead.state === 'triggered')) {
    const line = (id: string, price: number, color: string, title: string): PriceLineSpec =>
      ({ id: `5m-${id}`, price, color, width: 1, style: 'dashed', title, axisLabel: true });
    out.lines.push(
      line('trigger', s.trigger, SETUP_COLORS.trigger, '5m TRIGGER'),
      line('stop', s.stop, SETUP_COLORS.stop, '5m STOP'),
      line('target', s.target1, SETUP_COLORS.target, '5m TARGET'),
    );
  }
  return out;
}

export interface FiveMinuteChip {
  setupType: string;
  text: string;
  tip: string;
}

/** What the 1-minute pane shows of the 5-minute lanes: each one armed or near its trigger as a chip and a
 * dashed line at its trigger. */
export function fiveMinuteOnMinute(read: StockRead): { chips: FiveMinuteChip[]; lines: PriceLineSpec[] } {
  const chips: FiveMinuteChip[] = [];
  const lines: PriceLineSpec[] = [];
  for (const lane of read.setups_5m ?? []) {
    const s = lane.setup;
    if (!s || !IN_REACH.has(lane.state)) continue;
    const name = CHIP_NAMES[lane.setup_type] ?? setupName(lane.setup_type).toLowerCase();
    chips.push({
      setupType: lane.setup_type,
      text: `5m ${name} · ${lane.state} ${fmtPx(s.trigger)}`,
      tip: `A ${name} on 5-minute candles is ${lane.state === 'near' ? 'near' : 'armed at'} its ${fmtPx(s.trigger)} `
        + `trigger (stop ${fmtPx(s.stop)}, target ${fmtPx(s.target1)}). ${lane.reason}\n`
        + 'The 5-minute chart draws it; here it is only this chip and its trigger line. '
        + 'Nova scores 5-minute setups in silence: they never propose or trade.',
    });
    lines.push({ id: `5m-trigger:${lane.setup_type}`, price: s.trigger, color: SETUP_COLORS.trigger, width: 1,
      style: 'dashed', title: `5m ${name} trigger`, axisLabel: true });
  }
  return { chips, lines };
}
