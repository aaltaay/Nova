import { describe, expect, it } from 'vitest';
import type { Time } from 'lightweight-charts';
import { laneChip } from './chartShapes';
import { abcdPoints, abcdShapes, abcdStory, isAbcdLane } from './abcdShapes';
import { ABCD_COLORS, ABCD_DIM, ABCD_FADED, ABCD_PAST } from './constants';
import { laneShapes } from './laneShapes';
import { chartKey } from './paneKeyRows';
import { laneStory, type Episode } from './pastSetups';
import { pastShapes } from './pastShapes';
import type { AbcdPoints, SetupLane } from './types';

const toTime = (t: number) => t as unknown as Time;
const MIN = 60;
const HIGH_T = 600_000;
const A_T = HIGH_T + 14 * MIN;
const B_T = A_T + 5 * MIN;
const C_T = B_T + 2 * MIN;
// RXT 2026-05-08, the approved design's chart: a 5.30 high, A 4.88, B 5.18, C 4.98.
const POINTS: AbcdPoints = { high: [HIGH_T, 5.3], a: [A_T, 4.88], b: [B_T, 5.18], c: [C_T, 4.98], b_max: 5.3265,
  a_floor: 4.8556 };
const LEG = { t: A_T, high: 5.3, low: 4.88, pct: 0.0792, abcd: POINTS };
const ARMED = {
  trigger: 5.18, entry: 5.19, stop: 4.97, risk: 0.22, target1: 5.29, target2: 5.49, target1_fraction: 0.5,
  pullback_bars: 7, armed_bar_t: C_T, detail: { ...POINTS, stop_offset: 0.01, max_minutes: 20, deadline: A_T + 1200 },
} as unknown as SetupLane['setup'];

function lane(partial: Partial<SetupLane>): SetupLane {
  return {
    setup_type: 'abcd', state: 'armed', reason: 'A 4.88, B 5.18 under the 5.30 high, C 4.98', kind: 'abcd',
    chosen: false, level: 1, setup: ARMED, forming: null, leg: LEG, last_price: 5.1, distance: 0.08, grade: 'A',
    phase: null, tape: null, window: null, series: { bars_as_of: C_T + 2 * MIN }, ...partial,
  } as unknown as SetupLane;
}

describe('the ABCD on the 1-minute chart (watch only)', () => {
  it('is its own lane: the swings through A, B and C dashed in cyan, each point ringed and named', () => {
    expect(isAbcdLane('abcd')).toBe(true);
    expect(isAbcdLane('flat_top_breakout')).toBe(false);
    const d = laneShapes(lane({}), true, { toTime });
    expect(d.paths).toEqual([{ points: [{ t: HIGH_T, price: 5.3 }, { t: A_T, price: 4.88 }, { t: B_T, price: 5.18 },
      { t: C_T, price: 4.98 }], color: ABCD_COLORS.line, dashed: true }]);
    expect(d.dots.map(x => [x.label, x.labelBelow])).toEqual([['ABCD · buy over B · high 5.30', false], ['A 4.88', true],
      ['B 5.18', false], ['C 4.98', true]]);
    expect(d.dots.every(x => x.hoverId === 'lane:abcd')).toBe(true);
  });

  it('boxes the range from A and the two tolerances, and draws B\'s high to the edge while it waits', () => {
    const d = abcdShapes(lane({}), true, { toTime }, 'x');
    const [range, over, under] = d.boxes;
    expect(range).toMatchObject({ t1: A_T, t2: C_T + 2 * MIN, p1: 4.88, p2: 5.18, label: null, dashed: true });
    expect(over).toMatchObject({ t1: HIGH_T, p1: 5.3, p2: 5.3265, fill: ABCD_COLORS.band, stroke: null });
    expect(under).toMatchObject({ t1: A_T, p1: 4.8556, p2: 4.88, fill: ABCD_COLORS.band });
    expect(d.segments).toEqual([expect.objectContaining({ t1: B_T, price: 5.18, name: 'B', dashed: true })]);
    expect(d.marks).toEqual([]);
  });

  it('once it bought: the line runs solid to the break and the breaking candle gets a green D', () => {
    const t = C_T + 3 * MIN + 20;
    const d = abcdShapes(lane({ state: 'triggered', setup: { ...ARMED!, triggered_at: t } as SetupLane['setup'] }),
      true, { toTime }, 'x');
    expect(d.paths?.[0].dashed).toBe(false);
    expect(d.paths?.[0].points.at(-1)).toEqual({ t: C_T + 3 * MIN, price: 5.18 });
    expect(d.marks).toEqual([expect.objectContaining({ t: C_T + 3 * MIN, price: 5.18, label: 'D',
      color: ABCD_COLORS.go, dir: 'up' })]);
    expect(d.dots[0].label).toBe('ABCD · BOUGHT · high 5.30');
    expect(d.boxes[0]).toMatchObject({ t1: A_T, t2: C_T + 3 * MIN });
    expect(d.segments).toEqual([]);
  });

  it('not the plan\'s: dimmed, no words, no bands; failed: grey, saying why', () => {
    const dim = abcdShapes(lane({}), false, { toTime }, 'x');
    expect(dim.paths?.[0].color).toBe(ABCD_DIM.line);
    expect(dim.dots.every(x => x.label === null)).toBe(true);
    expect(dim.boxes.map(b => b.label)).toEqual([null]);
    const failed = abcdShapes(lane({ state: 'failed', setup: null, reason: 'a low of 4.80 undercut A 4.88' }), true,
      { toTime }, 'x');
    expect(failed.paths?.[0].color).toBe(ABCD_FADED.line);
    expect(failed.dots[0].label).toBe('ABCD · FAILED: a low of 4.80 undercut A 4.88 · high 5.30');
  });

  it('while it forms, says what it waits for; a leg from an older backend draws nothing', () => {
    const waiting = { ...POINTS, b: null, c: null };
    const d = abcdShapes(lane({ state: 'leg', setup: null, leg: { ...LEG, abcd: waiting } }), true, { toTime }, 'x');
    expect(d.dots[0].label).toBe('ABCD · waiting for B · high 5.30');
    expect(d.paths?.[0].points).toHaveLength(2);
    expect(abcdPoints({ leg: { t: 1, high: 2, low: 1, pct: 0.5 }, setup: null })).toBeNull();
    expect(abcdShapes(lane({ leg: { t: 1, high: 2, low: 1, pct: 0.5 }, setup: null }), true, { toTime }, 'x').boxes)
      .toEqual([]);
  });

  it('tells its story under the pointer, its chip says watch, and the Key lists its marks', () => {
    const story = abcdStory(lane({}));
    expect(story.title).toBe('ABCD · armed · watch only');
    expect(story.lines.some(l => l.startsWith('B 5.18'))).toBe(true);
    expect(story.lines).toContain('Buys 5.19 on the break of B · stop 4.97 (under C) · target 1 5.29');
    expect(laneStory(lane({}))).toEqual(story);
    expect(laneChip(lane({}), true).name).toBe('ABCD (watch)');
    const key = chartKey('full', { setups: true, levels: false, past: false, hidden: [] } as never);
    expect(key.map(s => s.title)).toContain('ABCD (watch only: never traded)');
  });

  it('a past ABCD keeps its range from A in faint cyan', () => {
    const ep = { setup_type: 'abcd', leg: LEG, setup: ARMED, started_at: A_T, triggered_at: C_T + 4 * MIN,
      ended_at: C_T + 20 * MIN, died_at: null, end: 'triggered', outcome: 'stop_first' } as unknown as Episode;
    const boxes = pastShapes([ep], { toTime });
    const mine = boxes.find(b => (b.label ?? '').startsWith('ABCD'));
    expect(mine).toMatchObject({ t1: A_T, p1: 4.88, p2: 5.18, stroke: ABCD_PAST.stroke, fill: ABCD_PAST.fill });
  });
});
