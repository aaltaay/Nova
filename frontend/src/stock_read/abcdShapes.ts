/**
 * The ABCD on the 1-minute pane (operator ask 2026-10-15, the approved design v1): a squeeze to the high, a pullback
 * (A), a push that fails to clear the high (B), a higher low (C), bought one cent over B (D). WATCH ONLY: drawn and
 * scored, never traded. Cyan, a colour no trade, level or other setup uses:
 *
 *   - a line through the high, A, B and C (and up to the break once it bought): dashed while it forms, solid once it
 *     bought;
 *   - a ring on each point, its letter and price beside it ("A 4.88", "B 5.18", under a low), and on the high where
 *     it stands ("ABCD · buy over B · high 5.30");
 *   - the range from A, between B's high and A's low, and the two tolerances as faint bands: how far B may
 *     double-top the high, how far C may sit under A;
 *   - B's high as a line to the right edge while it waits for the break, and a green triangle on the candle that
 *     broke it ("D").
 *
 * Not the plan's: the same in a dimmed cyan, without words or bands. A failed one grey, saying why. The backend reads
 * the shape (`setup_scanner/abcd_shape.py`): the leg carries the points `[time, price]` and the tolerances. The story
 * under the pointer is `abcdStory`. Pure: the lane in, the shapes out.
 */
import { ABCD_COLORS, ABCD_DIM, ABCD_FADED } from './constants';
import { emptyDraw, type LaneDraw } from './flatTopShapes';
import type { LaneDrawOptions } from './laneShapes';
import { fmtPx } from './planMath';
import type { SceneDot } from './sceneTypes';
import { hhmmEt } from './timeWords';
import type { AbcdPoints, SetupLane } from './types';

export const ABCD = 'abcd';
const WATCH_ONLY = 'Watch only: Nova draws and scores it, and never trades it.';
const MIN = 60;
/** The break's mark keeps its label's room before a run's. */
const BREAK_RANK = Number.MAX_SAFE_INTEGER;

export function isAbcdLane(setupType: string | null | undefined): boolean {
  return setupType === ABCD;
}

function num(x: unknown): number | null {
  return typeof x === 'number' && Number.isFinite(x) ? x : null;
}

type Pt = [number, number];

function isPt(x: unknown): x is Pt {
  return Array.isArray(x) && x.length === 2 && num(x[0]) !== null && num(x[1]) !== null;
}

/** The ABCD's points: the leg's, else the armed setup's detail; null from an older backend. */
export function abcdPoints(lane: Pick<SetupLane, 'leg' | 'setup'>): AbcdPoints | null {
  const fromLeg = lane.leg?.abcd;
  if (fromLeg && isPt(fromLeg.high)) return fromLeg;
  const d = lane.setup?.detail as Partial<AbcdPoints> | undefined;
  return d && isPt(d.high) ? { high: d.high, a: isPt(d.a) ? d.a : null, b: isPt(d.b) ? d.b : null,
    c: isPt(d.c) ? d.c : null, b_max: num(d.b_max) ?? d.high[1], a_floor: num(d.a_floor) } : null;
}

/** Where it stands, in the range box's few words. */
function stageWords(lane: SetupLane, pts: AbcdPoints, bought: boolean): string {
  if (lane.state === 'failed') return 'FAILED';
  if (bought) return 'BOUGHT';
  if (lane.forming?.blocked) return 'held back';
  if (lane.setup) return 'buy over B';
  if (!pts.a) return 'waiting for A';
  return 'waiting for B';
}

export function abcdShapes(lane: SetupLane, lead: boolean, o: LaneDrawOptions, hoverId: string): LaneDraw {
  const out = emptyDraw();
  const pts = abcdPoints(lane);
  if (!pts || !pts.high) return out;
  const failed = lane.state === 'failed';
  const c = failed ? ABCD_FADED : lead ? ABCD_COLORS : ABCD_DIM;
  const words = lead || failed;
  const setup = lane.setup && lane.state !== 'watching' ? lane.setup : null;
  const bought = lane.state === 'triggered' && setup !== null;
  const boughtAt = bought ? num(setup?.triggered_at) : null;
  const lastT = lane.series?.bars_as_of ?? null;
  const toT = (sec: number) => o.toTime(sec);

  // The swings: the high, A, B, C, and up to B's high on the candle that broke it.
  const swing = [pts.high, pts.a, pts.b, pts.c].filter(isPt);
  if (bought && boughtAt !== null && pts.b) swing.push([Math.floor(boughtAt / MIN) * MIN, pts.b[1]]);
  const line = swing.map(([t, price]) => ({ t: toT(t), price })).filter((p): p is { t: NonNullable<typeof p.t>; price: number } => p.t !== null);
  if (line.length > 1) out.paths = [{ points: line, color: c.line, dashed: !bought }];

  // The points: a ring each, its letter and price beside it (under a low).
  const ring = (pt: Pt | null, label: string | null, below: boolean) => {
    const t = pt ? toT(pt[0]) : null;
    if (!pt || t === null) return;
    const dot: SceneDot = { t, price: pt[1], color: c.line, fill: c.ring, label: words ? label : null,
      labelColor: c.text, labelBelow: below, hoverId };
    out.dots.push(dot);
  };
  const stage = `ABCD · ${stageWords(lane, pts, bought)}${failed ? `: ${lane.reason}` : ''}`;
  ring(pts.high, `${stage} · high ${fmtPx(pts.high[1])}`, false);
  ring(pts.a, pts.a ? `A ${fmtPx(pts.a[1])}` : null, true);
  ring(pts.b, pts.b ? `B ${fmtPx(pts.b[1])}` : null, false);
  ring(pts.c, pts.c ? `C ${fmtPx(pts.c[1])}` : null, true);

  // The range from A, between B's high and A's low; the tolerances as faint bands (the plan's only).
  const endT = boughtAt !== null ? Math.floor(boughtAt / MIN) * MIN : lastT;
  if (pts.a && endT !== null) {
    const t1 = toT(pts.a[0]);
    const t2 = toT(Math.max(pts.a[0], endT));
    const top = pts.b ? pts.b[1] : pts.high[1];
    if (t1 !== null && t2 !== null) {
      out.boxes.push({ t1, t2, p1: pts.a[1], p2: top, fill: c.fill, stroke: c.line, dashed: true,
        label: null, labelColor: c.text, hoverId });
      if (lead && !failed) {
        const hi = toT(pts.high[0]);
        if (hi !== null && pts.b_max > pts.high[1]) {
          out.boxes.push({ t1: hi, t2, p1: pts.high[1], p2: pts.b_max, fill: c.band, stroke: null, dashed: false,
            label: null, labelColor: c.text, hoverId });
        }
        if (pts.a_floor !== null && pts.a_floor < pts.a[1]) {
          out.boxes.push({ t1, t2, p1: pts.a_floor, p2: pts.a[1], fill: c.band, stroke: null, dashed: false,
            label: null, labelColor: c.text, hoverId });
        }
      }
    }
  }

  // B's high to the right edge while it waits for the break; the break itself, once bought.
  if (pts.b && !bought && !failed && setup) {
    const t = toT(pts.b[0]);
    if (t !== null) out.segments.push({ t1: t, price: pts.b[1], color: c.line, dashed: true, label: null, name: 'B' });
  }
  if (bought && boughtAt !== null && pts.b) {
    const t = toT(Math.floor(boughtAt / MIN) * MIN);
    if (t !== null) {
      out.marks.push({ t, price: pts.b[1], label: lead ? 'D' : '', color: c.go, rank: BREAK_RANK, dir: 'up', hoverId });
    }
  }
  return out;
}

/** The ABCD's story under the pointer: where it stands, its points, and its levels. */
export function abcdStory(lane: SetupLane): { title: string; lines: string[] } {
  const lines = [lane.reason || lane.state];
  const pts = abcdPoints(lane);
  if (pts?.high) {
    const at = (p: Pt | null, name: string, words: string) =>
      p ? `${name} ${fmtPx(p[1])} at ${hhmmEt(p[0])}: ${words}` : null;
    lines.push(...[
      at(pts.high, 'High', 'the squeeze to the high of day'),
      at(pts.a, 'A', 'the pullback\'s low'),
      at(pts.b, 'B', `the push that failed under the high (it may double-top up to ${fmtPx(pts.b_max)})`),
      at(pts.c, 'C', pts.a_floor !== null ? `the higher low so far (it holds over ${fmtPx(pts.a_floor)})` : 'the higher low so far'),
    ].filter((x): x is string => x !== null));
  }
  const s = lane.setup;
  if (s && lane.state !== 'watching') {
    lines.push(`${lane.state === 'triggered' ? 'Bought' : 'Buys'} ${fmtPx(s.entry)} on the break of B · stop `
      + `${fmtPx(s.stop)} (under C) · target 1 ${fmtPx(s.target1)}`);
  } else if (lane.forming?.blocked) {
    lines.push(`Held back: ${lane.forming.blocked}`);
  }
  lines.push(WATCH_ONLY);
  return { title: `ABCD · ${lane.state} · watch only`, lines };
}
