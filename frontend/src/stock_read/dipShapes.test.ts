import { describe, expect, it } from 'vitest';
import type { Time } from 'lightweight-charts';
import { laneChip } from './chartShapes';
import { DIP_COLORS, DIP_DIM, DIP_PAST } from './constants';
import { dipShapes, dipStory, isDipLane } from './dipShapes';
import { laneShapes } from './laneShapes';
import { laneStory } from './pastSetups';
import { pastShapes } from './pastShapes';
import type { Episode } from './pastSetups';
import type { SetupLane } from './types';

const toTime = (t: number) => t as unknown as Time;
const MIN = 60;
const LEG_T = 10_000;
const LEG = { t: LEG_T, high: 4.39, low: 3.99, pct: 0.1003 };

function lane(partial: Partial<SetupLane>): SetupLane {
  return {
    setup_type: 'pullback_dip', state: 'pullback', reason: '', kind: 'pullback_dip', chosen: false, level: 1,
    setup: null, forming: null, leg: LEG, last_price: 4.32, distance: null, grade: 'A', phase: null, tape: null,
    window: null, series: { bars_as_of: LEG_T + 2 * MIN }, ...partial,
  } as unknown as SetupLane;
}

const BOUGHT = {
  trigger: 4.32, entry: 4.33, stop: 4.23, risk: 0.1, target1: 4.39, target2: 4.49, target1_fraction: 0.5,
  pullback_bars: 2, armed_bar_t: LEG_T + 2 * MIN, triggered_at: LEG_T + 3 * MIN,
  detail: { entry_mode: 'wick', entry_bar_t: LEG_T + 2 * MIN, wick_pct: 0.7778, close_pct: 0.8889, lower_wick: 0.07,
    red_bars: 1, pullback_low: 4.24, pullback_high: 4.39 },
} as unknown as SetupLane['setup'];

describe('the pullback dip on the 1-minute chart (#847, watch only)', () => {
  it('is its own lane, in pink: the leg, the pullback it waits in (dashed) and what it wants', () => {
    expect(isDipLane('pullback_dip')).toBe(true);
    expect(isDipLane('first_pullback')).toBe(false);
    const waiting = lane({ forming: { trigger: 4.32, entry: 4.33, stop: 4.29, risk: 0.04, target1: 4.39, bars: 1,
      blocked: null, waiting: 'a bottoming wick' } as SetupLane['forming'] });
    const d = laneShapes(waiting, true, { toTime });
    expect(d.boxes.map(b => b.label)).toEqual(['LEG +10.0%', 'DIP 1 · wants a wick']);
    expect(d.boxes[1]).toMatchObject({ t1: LEG_T + MIN, t2: LEG_T + 2 * MIN, p1: 4.29, p2: 4.39, dashed: true,
      stroke: DIP_COLORS.line, hoverId: 'lane:pullback_dip' });
    expect(d.dots).toEqual([]);
  });

  it('once it bought, the pullback is solid, the entry candle boxed to its close and a bottoming wick ringed', () => {
    const d = dipShapes(lane({ state: 'triggered', setup: BOUGHT }), true, { toTime }, MIN, 'lane:pullback_dip');
    const [legBox, pullback, candle] = d.boxes;
    expect(legBox.label).toBe('LEG +10.0%');
    expect(pullback).toMatchObject({ label: 'DIP · WICK', dashed: false, p1: 4.24, p2: 4.39, t2: LEG_T + 2 * MIN });
    expect(candle).toMatchObject({ t1: LEG_T + 2 * MIN, t2: LEG_T + 2 * MIN, p1: 4.24, p2: 4.32, label: null });
    expect(d.dots).toEqual([expect.objectContaining({ price: 4.24, label: 'bottom', color: DIP_COLORS.line })]);

    const green = { ...BOUGHT, detail: { ...(BOUGHT!.detail ?? {}), entry_mode: 'green' } } as SetupLane['setup'];
    const g = dipShapes(lane({ state: 'triggered', setup: green }), true, { toTime }, MIN, 'x');
    expect(g.boxes[1].label).toBe('DIP · 1ST GREEN');
    expect(g.dots).toEqual([]);                       // the first green close has no wick to ring
  });

  it('not the plan\'s: dimmed and unlabelled, no leg box (the first pullback draws that leg); failed: nothing', () => {
    const d = dipShapes(lane({ state: 'triggered', setup: BOUGHT }), false, { toTime }, MIN, 'x');
    expect(d.boxes.map(b => b.label)).toEqual([null, null]);
    expect(d.boxes[0].stroke).toBe(DIP_DIM.line);
    expect(d.dots[0].label).toBeNull();
    expect(dipShapes(lane({ state: 'failed', reason: 'gave back half the leg' }), true, { toTime }, MIN, 'x').boxes)
      .toEqual([]);
  });

  it('a blocked entry candle says it is held back', () => {
    const blocked = lane({ forming: { trigger: 4.32, entry: 4.33, stop: 4.23, risk: 0.1, target1: 4.39, bars: 2,
      blocked: 'risk 0.10 is over 0.08', waiting: null } as SetupLane['forming'] });
    expect(dipShapes(blocked, true, { toTime }, MIN, 'x').boxes[1].label).toBe('DIP 2 · held back');
  });

  it('tells its story under the pointer and says it is watch only', () => {
    const s = laneStory(lane({ state: 'triggered', reason: 'bought the dip', setup: BOUGHT }));
    expect(s.title).toBe('Pullback dip · triggered · watch only');
    expect(s.lines.join('\n')).toContain('a bottoming wick (78% of the candle, closing 89% up it)');
    expect(s.lines.join('\n')).toContain('Entry 4.33 · stop 4.23 (under the pullback\'s low) · target 1 4.39');
    expect(s.lines.at(-1)).toBe('Watch only: Nova draws and scores it, and never trades it.');
    const waiting = dipStory(lane({ forming: { trigger: 4.32, entry: 4.33, stop: 4.29, risk: 0.04, target1: 4.39,
      bars: 1, blocked: null, waiting: 'a bottoming wick' } as SetupLane['forming'] }));
    expect(waiting.lines[2]).toContain('Waits for a bottoming wick');
  });

  it('names its legend chip as watch only', () => {
    expect(laneChip(lane({ state: 'triggered', setup: BOUGHT })).text).toBe('Dip (watch) triggered');
  });

  it('a past dip that bought keeps its pullback in faint pink; one that died draws nothing', () => {
    const ep: Episode = {
      id: 'e1', setup_type: 'pullback_dip', end: 'triggered', leg: LEG, setup: BOUGHT, started_at: LEG_T,
      triggered_at: LEG_T + 3 * MIN, ended_at: LEG_T + 3 * MIN, died_at: null, died_bar_t: null, after: null,
      reason: null, ended_by: null, reached: 'triggered', filtered: null, trigger_price: 4.32,
      score: { outcome: 'target_first', bar_r: 0.6, exit_reason: 'target' },
    };
    const boxes = pastShapes([ep], { toTime });
    expect(boxes).toHaveLength(1);
    expect(boxes[0]).toMatchObject({ p1: 4.24, p2: 4.39, stroke: DIP_PAST.stroke, dashed: true });
    expect(boxes[0].label).toMatch(/^DIP · /);
    expect(pastShapes([{ ...ep, setup: null, end: 'failed', died_at: LEG_T + 4 * MIN } as unknown as Episode],
      { toTime })).toEqual([]);
  });
});
