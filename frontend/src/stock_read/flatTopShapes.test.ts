import { describe, expect, it } from 'vitest';
import type { Time } from 'lightweight-charts';
import { FLAT_TOP_COLORS, FLAT_TOP_DIM, FLAT_TOP_FADED } from './constants';
import { flatTopShapes, flatTopStory, flatTopTouches } from './flatTopShapes';
import { laneShapes } from './laneShapes';
import { normalizeLeg } from './normalize';
import { normalizePastSetups } from './pastSetups';
import { pastHoverId, pastRings } from './pastShapes';
import type { SetupLane, SetupLevels } from './types';

/** NAUT 2026-09-30, the operator's kind of flat top: a run to 1.53 at 07:09, five more candles tapping 1.53 on rising
 * lows, the break at 07:15 and the hold at 07:16 (IBKR's 1-minute bars). */
const ET0 = Date.UTC(2026, 8, 30, 11, 0) / 1000;      // 07:00 ET
const at = (min: number) => ET0 + min * 60;
const identity = (s: number) => s as Time;
const TOUCHES: [number, number][] = [[at(9), 1.53], [at(10), 1.53], [at(11), 1.53], [at(12), 1.53], [at(13), 1.53],
  [at(14), 1.53]];
const LEG = { t: at(9), high: 1.53, low: 1.46, pct: 0.0479, bars: 5, touches: TOUCHES, zone: 1.52 };
const ARMED: SetupLevels = {
  trigger: 1.53, entry: 1.54, stop: 1.505, risk: 0.035, target1: 1.61, pullback_bars: 5, armed_bar_t: at(14),
  detail: { entry_mode: 'hold', base_low: 1.505, broke_at: null, broke_bar_t: null, hold_bars: 3, touches: TOUCHES,
    zone: 1.52, min_touches: 3 },
};

function lane(state: string, over: Partial<SetupLane> = {}): SetupLane {
  return {
    setup_type: 'flat_top_breakout', state, reason: 'flat top 1.53: 6 touches, a base of 5 candles', kind: 'flat_top_breakout',
    chosen: false, level: 2, setup: ARMED, forming: null, leg: LEG, last_price: 1.53, distance: 0, grade: 'B', phase: null,
    tape: null, window: { start: '07:00', end: '11:30', state: 'open' },
    series: { bars_as_of: at(14), close: 1.525, ema: 1.51, macd_line: 0.01, macd_signal: 0.005, macd_hist: 0.005, hod: 1.53 },
    timeframe: '1m', ...over,
  };
}

const forming = lane('leg', {
  setup: null, reason: 'flat top 1.53: 2 of 3 touches -- 1 more tap of it arms it',
  forming: { trigger: 1.53, entry: 1.54, stop: 1.505, risk: 0.035, target1: 1.61, bars: 2, blocked: null,
    waiting: '1 more touch' },
  leg: { ...LEG, bars: 1, touches: TOUCHES.slice(0, 2) },
  series: { bars_as_of: at(10), close: 1.52, ema: 1.5, macd_line: 0.01, macd_signal: 0.005, macd_hist: 0.005, hod: 1.53 },
});
const near = lane('near', {
  reason: 'broke the 1.53 high -- the first of the next 3 candles that holds over it and closes green is the entry',
  setup: { ...ARMED, detail: { ...ARMED.detail, broke_at: at(15) + 20, broke_bar_t: at(15) } },
});
const triggered = lane('triggered', {
  reason: 'held over 1.53: a green candle closed at 1.56 -- entry 1.57, stop 1.53',
  setup: { ...ARMED, entry: 1.572, stop: 1.53, risk: 0.042, target1: 1.656, triggered_at: at(17), trigger_price: 1.562,
    detail: { ...ARMED.detail, broke_at: at(15) + 20, broke_bar_t: at(15), hold_bar_t: at(16), hold_high: 1.562 } },
});
const opts = { toTime: identity, highAt: (t: number) => (t === at(15) ? 1.57 : null) };

describe('the flat top drawn as the operator sketched it', () => {
  it('forms from its second touch: a dashed line, the touches ringed and counted, the base boxed', () => {
    const d = flatTopShapes(forming, true, opts, 60, 'lane:flat_top_breakout', '');
    expect(d.segments).toEqual([{ t1: at(9), price: 1.53, color: FLAT_TOP_COLORS.line, dashed: true, label: null }]);
    expect(d.dots.map(x => [x.t, x.price, x.label])).toEqual([[at(9), 1.53, null], [at(10), 1.53, '2 of 3 touches']]);
    expect(d.boxes).toHaveLength(1);
    expect(d.boxes[0]).toMatchObject({ t1: at(9), t2: at(10), p1: 1.505, p2: 1.53, dashed: true, label: 'BASE 1' });
    expect(d.words.map(w => w.text)).toEqual(['FLAT TOP = HOD 1.53']);
    expect(d.marks).toEqual([]);
  });

  it('armed: a solid line, every touch ringed, the last one counting them', () => {
    const d = flatTopShapes(lane('armed'), true, opts, 60, 'lane:flat_top_breakout', '');
    expect(d.segments[0].dashed).toBe(false);
    expect(d.words.map(w => w.text)).toEqual(['FLAT TOP = HOD 1.53']);
    // Near it (the tape is read) is not over it: still the high of day.
    expect(flatTopShapes(lane('near'), true, opts, 60, 'x', '').words.map(w => w.text)).toEqual(['FLAT TOP = HOD 1.53']);
    expect(d.dots).toHaveLength(6);
    expect(d.dots.at(-1)?.label).toBe('6 touches');
    expect(d.dots.every(x => x.fill === FLAT_TOP_COLORS.ring && x.hoverId === 'lane:flat_top_breakout')).toBe(true);
    expect(d.boxes[0]).toMatchObject({ t1: at(9), t2: at(14), p1: 1.505, p2: 1.53, label: 'BASE 5' });
  });

  it('marks the break over its candle and, once it held, boxes the hold candle', () => {
    const n = flatTopShapes(near, true, opts, 60, 'lane:flat_top_breakout', '');
    expect(n.marks).toEqual([{ t: at(15), price: 1.57, label: 'break', color: FLAT_TOP_COLORS.go,
      rank: Number.MAX_SAFE_INTEGER, dir: 'up' }]);
    expect(n.words.map(w => w.text)).toEqual(['FLAT TOP 1.53']);         // no longer the high of day once broken
    const t = flatTopShapes(triggered, true, opts, 60, 'lane:flat_top_breakout', '');
    expect(t.marks).toHaveLength(1);
    const hold = t.boxes.find(b => b.label === 'hold');
    expect(hold).toMatchObject({ t1: at(16), t2: at(16), p1: 1.53, p2: 1.562, stroke: FLAT_TOP_COLORS.go });
    expect(t.boxes.find(b => b.label === 'BASE 5')?.p1).toBe(1.505);   // the base keeps its own low, not the hold's
  });

  it('a lane that is not the plan\'s is a dimmed violet with no counts, edge word or marks; a failed one is grey', () => {
    const d = flatTopShapes(triggered, false, opts, 60, 'lane:flat_top_breakout', '');
    expect(d.dots.every(x => x.label === null && x.color === FLAT_TOP_DIM.ringStroke)).toBe(true);
    expect(d.words).toEqual([]);
    expect(d.marks).toEqual([]);
    expect(d.segments[0].label).toBe('FLAT TOP 1.53');
    const failed = flatTopShapes(lane('failed', { setup: null, reason: 'closed back under the 1.53 high' }), true, opts, 60,
      'lane:flat_top_breakout', ' · FAILED: closed back under');
    expect(failed.segments[0]).toMatchObject({ color: FLAT_TOP_FADED.line, label: 'FLAT TOP 1.53 · FAILED: closed back under' });
    expect(failed.dots.every(x => x.color === FLAT_TOP_FADED.ringStroke)).toBe(true);
  });

  it('laneShapes hands the flat top to its own drawing; an older backend without touches still draws the base', () => {
    const d = laneShapes(lane('armed', { leg: { t: at(9), high: 1.53, low: 1.46, pct: 0.0479, bars: 5 },
      setup: { ...ARMED, detail: { entry_mode: 'hold', base_low: 1.505 } } }), true, opts);
    expect(d.dots).toEqual([]);
    expect(d.boxes[0]).toMatchObject({ p1: 1.505, p2: 1.53 });
    expect(d.segments).toHaveLength(1);
  });

  it('tells the touches, the base and the hold under the pointer', () => {
    const s = flatTopStory(triggered);
    expect(s.title).toBe('Flat top 1.53 · triggered');
    expect(s.lines.join('\n')).toContain('6 touches: 07:09 1.53 · 07:10 1.53');
    expect(s.lines.join('\n')).toContain('Base: 5 candles after the first touch, low 1.50');
    expect(s.lines.join('\n')).toContain('each high within 0.01 under the high counts');
    expect(s.lines.join('\n')).toContain('Held at 07:16: entry 1.57, stop 1.53');
  });
});

describe('the flat top on the wire and in the past', () => {
  it('keeps the touches and the zone of a leg, and drops a malformed touch', () => {
    const leg = normalizeLeg({ ...LEG, touches: [[at(9), 1.53], ['x', 1], [at(10)]] });
    expect(leg?.touches).toEqual([[at(9), 1.53]]);
    expect(leg?.zone).toBe(1.52);
    expect(normalizeLeg({ t: 1, high: 2, low: 1, pct: 0.1 })).not.toHaveProperty('touches');
    expect(flatTopTouches({ leg: null, setup: ARMED })).toHaveLength(6);   // the armed setup's, when the leg has none
  });

  it('a past flat top keeps its touches as faint rings that tell its story', () => {
    const past = normalizePastSetups({ symbol: 'NAUT', date: '2026-09-30', generated_at: at(40), episodes: [{
      id: 'NAUT-flat_top_breakout-1', setup_type: 'flat_top_breakout', started_at: at(10), ended_at: at(30),
      end: 'triggered', died_at: null, died_bar_t: null, reason: null, ended_by: null, reached: 'triggered', leg: LEG,
      setup: triggered.setup, filtered: null, triggered_at: at(17), trigger_price: 1.562, score: null, after: null,
    }] })!.episodes;
    const rings = pastRings(past, { toTime: identity });
    expect(rings).toHaveLength(6);
    expect(rings.every(r => r.hoverId === pastHoverId(past[0]) && r.label === undefined)).toBe(true);
  });
});
