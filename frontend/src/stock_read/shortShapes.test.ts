import { describe, expect, it } from 'vitest';
import type { Time } from 'lightweight-charts';
import { SHORT_SETUP_COLORS } from '../constantGroups/short_setups';
import { laneShapes } from './laneShapes';
import { pastShapes } from './pastShapes';
import { pastStory, type Episode } from './pastSetups';
import type { SetupLane } from './types';

const toTime = (t: number) => t as unknown as Time;
const T = 1_791_400_000 - (1_791_400_000 % 60);

function lane(partial: Partial<SetupLane>): SetupLane {
  return {
    setup_type: 'bear_flag', side: 'short', state: 'armed', reason: '', kind: 'bear_flag', chosen: false, level: 1,
    setup: { trigger: 5.40, entry: 5.39, stop: 5.53, risk: 0.14, target1: 5.11, pullback_bars: 2, armed_bar_t: T + 180 },
    forming: null, leg: { t: T, high: 5.6, low: 5.2, pct: 0.071, bars: 3 }, last_price: 5.44, distance: 0.04,
    grade: 'B', phase: null, tape: null, window: null, series: { bars_as_of: T + 180, close: 5.44, ema: 5.45,
      macd_line: -0.01, macd_signal: 0, macd_hist: -0.01, hod: 6.01 },
    ...partial,
  } as SetupLane;
}

describe('short setups on the 1-minute chart (ADR 049)', () => {
  it('draws a bear flag in orange, labelled ▼: its pole, then its flag between the trigger and the buy stop', () => {
    const draw = laneShapes(lane({}), true, { toTime });
    expect(draw.boxes.map(b => b.label)).toEqual(['▼ POLE −7.1%', '▼ SHORT · FLAG 2']);
    const flag = draw.boxes[1];
    expect([flag.p1, flag.p2]).toEqual([5.40, 5.53]);
    expect(flag.stroke).toBe(SHORT_SETUP_COLORS.stroke);
    expect(draw.boxes[0].t1).toBe(T - 2 * 60);                     // three red candles, the last at the leg
  });

  it('fades a short that is not the plan\'s, and says the rule a failed one broke', () => {
    const faded = laneShapes(lane({}), false, { toTime });
    expect(faded.boxes[1].stroke).not.toBe(SHORT_SETUP_COLORS.stroke);
    const failed = laneShapes(lane({ state: 'failed', reason: 'the flag took back 61% of the pole -- more than 50%' }),
      true, { toTime });
    expect(failed.boxes[1].label).toBe('▼ SHORT · FLAG 2 · FAILED: flag too deep');
  });

  it('draws the flat top a failed breakout poked over, the VWAP a lost VWAP lost, and the SSR bounce\'s resting short', () => {
    const fb = laneShapes(lane({ setup_type: 'failed_breakout', leg: { t: T, high: 5.62, low: 5.50, pct: 0.02,
      touches: [[T - 600, 5.50], [T - 300, 5.49]] } }), true, { toTime });
    expect(fb.segments[0]).toMatchObject({ t1: T - 600, price: 5.50, label: 'FLAT TOP 5.50' });
    expect(fb.boxes[0].label).toBe('▼ SHORT · FAILED BACK UNDER');
    const lv = laneShapes(lane({ setup_type: 'lost_vwap', leg: { t: T, high: 5.71, low: 5.55, pct: 0 } }), true, { toTime });
    expect(lv.segments[0]).toMatchObject({ price: 5.71, label: 'LOST VWAP 5.71' });
    const ssr = laneShapes(lane({ setup_type: 'ssr_bounce', leg: { t: T, high: 5.04, low: 4.66, pct: 0.08 },
      setup: { trigger: 4.99, entry: 4.99, stop: 5.09, risk: 0.10, target1: 4.79, armed_bar_t: T + 120,
        detail: { level: 5.0, level_kind: 'round' } } }), true, { toTime });
    expect(ssr.boxes[0].label).toBe('▼ DROP −8.0% · SSR');
    expect(ssr.segments.map(s => s.label)).toEqual(['LEVEL 5.00', '▼ SHORT RESTS 4.99']);
  });
});

function episode(partial: Partial<Episode> = {}): Episode {
  return {
    id: 'e1', setup_type: 'backside_lower_high', started_at: T, ended_at: T + 600, end: 'failed', died_at: T + 300,
    died_bar_t: T + 300, reason: 'the bounce reached the high of day -- not a lower high', ended_by: null,
    reached: 'armed', leg: { t: T, high: 6.01, low: 5.46, pct: 0.092 },
    setup: { trigger: 5.52, entry: 5.51, stop: 5.66, risk: 0.15, target1: 5.21 }, filtered: null,
    triggered_at: null, trigger_price: null, score: null,
    after: { from_ts: T + 300, price: 5.6, level: 5.52, entry: 5.51, floor: 5.66, window_min: 15, complete: true,
      bars: 15, high: 5.7, low: 5.4, first: 'low', crossed_at: T + 420,
      trade: { entry: 5.51, stop: 5.66, risk: 0.15, target: 5.21, outcome: 'target_first', outcome_at: T + 900,
        bar_r: 1.4, exit_reason: 'target', mfe_r: 2.1, mae_r: -0.3 } },
    ...partial,
  };
}

describe('a short setup that ended (ADR 049)', () => {
  it('stays on the chart in orange, ▼ SHORT, between its trigger and its buy stop', () => {
    const boxes = pastShapes([episode()], { toTime });
    expect(boxes.map(b => b.label)).toEqual(['▼ FADE', '▼ SHORT · ✕ bounce made the high · ↘ then broke down']);
    expect([boxes[1].p1, boxes[1].p2]).toEqual([5.52, 5.66]);
  });

  it('tells its story the short way: its fade, its levels, and the breakdown that came next', () => {
    const { lines } = pastStory(episode());
    expect(lines).toContain('Armed ▼ SHORT: under 5.52, buy stop 5.66, cover 5.21');
    expect(lines.some(l => l.startsWith('Fade −9.2% off the 6.01 high of day, to 5.46'))).toBe(true);
    expect(lines.some(l => /under 5\.52 first at .* \(the breakdown it waited for\), before 5\.66\./.test(l))).toBe(true);
    expect(lines.some(l => l.startsWith('The refused short: under 5.51, buy stop 5.66, cover 5.21 -- the cover came first'))).toBe(true);
  });
});
