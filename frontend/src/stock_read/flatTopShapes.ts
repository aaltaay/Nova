/**
 * The flat top drawn the way the operator sketched it (2026-10-06: "Make it something special like this ... when
 * it starts forming"). A violet line at the level the candles keep tapping, from the first touch to the pane's
 * right edge: dashed while it forms, solid once it is armed. A ring on every touch, the last one counting them ("4
 * touches", or "2 of 3 touches" while it forms). The base boxed from the first touch, between its low and the
 * level. A green triangle over the candle that broke it ("break"), and the candle that held it boxed green
 * ("hold"): the entry. The level's name goes to the pane's right edge ("FLAT TOP = HOD 5.50" while it is the high
 * of day). A lane that is not the plan's draws the same shapes in a dimmed violet, unlabelled, and a failed one
 * grey. The backend reads the shape
 * (`setup_scanner/flat_top_shape.py`): the leg carries the touches as `[time, high]`, the armed setup's detail the
 * zone, the break's candle and the hold's. Pure: the lane in, the shapes out.
 */
import { EDGE_PRIORITY } from '../chart';
import { FLAT_TOP_COLORS, FLAT_TOP_DIM, FLAT_TOP_FADED } from './constants';
import type { LaneDrawOptions } from './laneShapes';
import { fmtPx, fmtStep } from './planMath';
import type { SceneBox, SceneDot, SceneMark, SceneSegment, SceneWord } from './sceneTypes';
import { hhmmEt } from './timeWords';
import type { SetupLane } from './types';

export const FLAT_TOP = 'flat_top_breakout';
/** The flat top's name in the edge column: over VWAP's and the levels', under the plan's lines. */
const WORD_PRIORITY = EDGE_PRIORITY.vwap + 10;
/** The break's label keeps its room before any run's. */
const BREAK_RANK = Number.MAX_SAFE_INTEGER;

/** Everything a lane draws: the boxes and lines every lane has, and the flat top's rings, marks and edge word. */
export interface LaneDraw {
  boxes: SceneBox[];
  segments: SceneSegment[];
  dots: SceneDot[];
  marks: SceneMark[];
  words: SceneWord[];
}

export function emptyDraw(): LaneDraw {
  return { boxes: [], segments: [], dots: [], marks: [], words: [] };
}

export type Touch = [number, number];

function num(x: unknown): number | null {
  return typeof x === 'number' && Number.isFinite(x) ? x : null;
}

function isTouch(x: unknown): x is Touch {
  return Array.isArray(x) && x.length === 2 && num(x[0]) !== null && num(x[1]) !== null;
}

/** The flat top's touches, `[time, high]` oldest first: the leg's, else the armed setup's; none from an older
 * backend. */
export function flatTopTouches(lane: Pick<SetupLane, 'leg' | 'setup'>): Touch[] {
  const fromLeg = lane.leg?.touches;
  if (Array.isArray(fromLeg) && fromLeg.length) return fromLeg.filter(isTouch);
  const fromSetup = lane.setup?.detail?.touches;
  return Array.isArray(fromSetup) ? fromSetup.filter(isTouch) : [];
}

/** How many touches arm it: the armed setup's rule, else what the forming one still waits for. */
export function touchesNeeded(lane: Pick<SetupLane, 'setup' | 'forming'>, have: number): number | null {
  const rule = num(lane.setup?.detail?.min_touches);
  if (rule !== null) return rule;
  const more = /^(\d+) more touch/.exec(lane.forming?.waiting ?? '');
  return more ? have + Number(more[1]) : null;
}

function touchWords(n: number): string {
  return `${n} touch${n === 1 ? '' : 'es'}`;
}

/** The candle the break printed in: the hold entry's noted candle, else (the break entry) the trigger's. */
export function breakBar(lane: Pick<SetupLane, 'setup'>, bar: number): number | null {
  const s = lane.setup;
  const noted = num(s?.detail?.broke_bar_t);
  if (noted !== null) return noted;
  const at = num(s?.triggered_at);
  return s?.detail?.entry_mode === 'break' && at !== null ? Math.floor(at / bar) * bar : null;
}

export function flatTopShapes(lane: SetupLane, lead: boolean, o: LaneDrawOptions, bar: number, hoverId: string,
  tag: string): LaneDraw {
  const out = emptyDraw();
  const leg = lane.leg;
  if (!leg) return out;
  const touches = flatTopTouches(lane);
  const setup = lane.setup && lane.state !== 'watching' ? lane.setup : null;
  const forming = lane.forming;
  if (!setup && !forming && touches.length < 2) return out;
  const failed = lane.state === 'failed';
  const bright = lead && !failed;
  const c = bright ? FLAT_TOP_COLORS : failed ? FLAT_TOP_FADED : FLAT_TOP_DIM;
  const level = setup?.trigger ?? forming?.trigger ?? leg.high;
  const baseLow = num(setup?.detail?.base_low) ?? forming?.stop ?? setup?.stop ?? null;
  const lastT = lane.series?.bars_as_of ?? null;
  const endT = setup?.armed_bar_t ?? lastT;
  const t1 = o.toTime(leg.t);

  // The base: from the first touch to the last candle under it, between its low and the level.
  if (baseLow !== null && baseLow < level && endT !== null) {
    const tEnd = o.toTime(Math.max(endT, leg.t));
    if (t1 !== null && tEnd !== null) {
      out.boxes.push({ t1, t2: tEnd, p1: baseLow, p2: level, fill: c.fill, stroke: c.line, dashed: true,
        label: `BASE ${leg.bars ?? ''}`.trim() + tag, labelColor: c.text, labelBelow: true, hoverId });
    }
  }
  // The level, to the right edge: its name is the edge column's while it leads, the line's own when faded.
  if (t1 !== null) {
    out.segments.push({ t1, price: level, color: c.line, dashed: !setup,
      label: bright ? null : `FLAT TOP ${fmtPx(level)}${failed ? tag : ''}` });
  }
  if (bright) {
    // Still the high of day until a price breaks it: near it is not over it.
    const hod = lane.state !== 'triggered' && num(setup?.detail?.broke_at) === null;
    out.words.push({ id: `flat:${hoverId}`, text: `FLAT TOP${hod ? ' = HOD' : ''} ${fmtPx(level)}`, color: c.line,
      priority: WORD_PRIORITY, price: level, series: null, valueWhenOff: false });
  }
  // Every touch ringed on its candle's high; the last one counts them.
  const need = touchesNeeded(lane, touches.length);
  const count = !setup && need !== null && need > touches.length
    ? `${touches.length} of ${touchWords(need)}` : touchWords(touches.length);
  touches.forEach(([t, high], i) => {
    const at = o.toTime(t);
    if (at === null) return;
    out.dots.push({ t: at, price: high, color: c.ringStroke, fill: c.ring,
      label: bright && i === touches.length - 1 ? count : null, labelColor: c.text, hoverId });
  });
  if (!bright || !setup) return out;
  // The break, over its candle's high, and the candle that held it: the entry.
  const brk = breakBar(lane, bar);
  const tb = brk !== null ? o.toTime(brk) : null;
  if (brk !== null && tb !== null) {
    out.marks.push({ t: tb, price: o.highAt?.(brk) ?? level, label: 'break', color: c.go, rank: BREAK_RANK, dir: 'up' });
  }
  const holdT = num(setup.detail?.hold_bar_t);
  const th = lane.state === 'triggered' && holdT !== null ? o.toTime(holdT) : null;
  if (holdT !== null && th !== null) {
    const high = num(setup.detail?.hold_high) ?? setup.trigger_price ?? level;
    out.boxes.push({ t1: th, t2: th, p1: setup.stop, p2: high, fill: c.holdFill, stroke: c.go, dashed: false,
      label: 'hold', labelColor: c.go, hoverId });
  }
  return out;
}

/** The flat top's story under the pointer: where it stands, every touch, the base, and how it enters. */
export function flatTopStory(lane: SetupLane): { title: string; lines: string[] } {
  const touches = flatTopTouches(lane);
  const setup = lane.setup;
  const detail = setup?.detail ?? {};
  const level = setup?.trigger ?? lane.forming?.trigger ?? lane.leg?.high ?? null;
  const lines = [lane.reason || lane.state];
  if (touches.length) {
    const zone = num(detail.zone) ?? num(lane.leg?.zone);
    const within = level !== null && zone !== null && level > zone
      ? ` -- each high within ${fmtStep(level - zone, level)} under the high counts` : '';
    lines.push(`${touchWords(touches.length)}: ${touches.map(([t, h]) => `${hhmmEt(t)} ${fmtPx(h)}`).join(' · ')}${within}`);
  }
  const baseLow = num(detail.base_low) ?? lane.forming?.stop ?? null;
  if (lane.leg?.bars) {
    lines.push(`Base: ${lane.leg.bars} candles after the first touch${baseLow !== null ? `, low ${fmtPx(baseLow)}` : ''}`);
  }
  const broke = num(detail.broke_at);
  if (broke !== null) lines.push(`Broke over ${fmtPx(level)} at ${hhmmEt(broke)}`);
  const hold = num(detail.hold_bar_t);
  if (lane.state === 'triggered' && setup && hold !== null) {
    lines.push(`Held at ${hhmmEt(hold)}: entry ${fmtPx(setup.entry)}, stop ${fmtPx(setup.stop)}, target ${fmtPx(setup.target1)}`);
  } else if (setup && detail.entry_mode !== 'break') {
    lines.push('The entry, the taught way: after a price over it, the first candle that holds it (its low in the '
      + 'touch zone or over it) and closes green over it. A close back under the zone fails it.');
  }
  return { title: `Flat top${level !== null ? ` ${fmtPx(level)}` : ''} · ${lane.state}`, lines };
}
