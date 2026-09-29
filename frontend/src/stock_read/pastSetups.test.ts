import type { Time } from 'lightweight-charts';
import { describe, expect, it } from 'vitest';
import { laneHoverId, paneDraw } from './chartShapes';
import { normalizeStockRead } from './normalize';
import {
  drawnPast,
  endOf,
  failingNow,
  laneStory,
  normalizePastSetups,
  pastCounts,
  pastLabel,
  pastStory,
  shortReason,
  type Episode,
} from './pastSetups';
import { pastHoverId, pastShapes } from './pastShapes';
import { SetupShapesPrimitive, type SceneBox } from './SetupShapesPrimitive';
import { parseLayers } from './StockReadContext';
import { apusReadWire } from './stockReadFixtures';
import type { StockRead } from './types';

const LAYERS = { setups: true, levels: true, past: true, hidden: [] as string[], plan: 'auto' as const };
const identity = (sec: number) => sec as Time;
/** A moment of 2026-09-29, Eastern (EDT), as epoch seconds. */
const MIDNIGHT_ET = Date.parse('2026-09-29T00:00:00-04:00') / 1000;
const at = (h: number, m: number, s = 0) => MIDNIGHT_ET + h * 3600 + m * 60 + s;

/** NCPL's bull flag on 2026-09-29, exactly as `GET /api/stock-read/NCPL/past-setups` answered it: the pole
 * failed at 09:20 ("flag candle 2 made a higher high"), left the scanner at 09:21, and price then went over
 * the pole's 1.35 high before its 1.31 flag low. */
const ncplFlag = {
  id: 'NCPL-bull_flag-1790687880279', symbol: 'NCPL', setup_type: 'bull_flag', template: 'default', rev: 1,
  started_at: at(9, 18, 0.28), ended_at: at(9, 21, 0.3), end: 'failed', died_at: at(9, 20, 0.42), died_bar_t: at(9, 19),
  reason: 'flag candle 2 made a higher high than the candle before it',
  reason_key: 'flag candle # made a higher high than the candle before it', ended_by: 'no pole', reached: 'leg',
  leg: { t: at(9, 17), high: 1.35, low: 1.27, pct: 0.063, bars: 3, start: 192, top: 194, volume: 18053.7 },
  setup: null, setup_id: null, filtered: null, triggered_at: null, trigger_price: null, score: null,
  after: {
    from_ts: at(9, 20, 0.42), price: 1.3303, level: 1.35, entry: 1.36, floor: 1.31, window_min: 15, complete: true,
    bars: 15, high: 1.43, low: 1.32, first: 'high', crossed_at: at(9, 20),
    trade: { entry: 1.36, stop: 1.31, risk: 0.05, target: 1.46, outcome: 'open', outcome_at: null, bar_r: -0.194,
      exit_reason: 'bailout', mfe_r: 1.4, mae_r: -0.8 },
  },
};
const fpTriggered = {
  ...ncplFlag, id: 'NCPL-first_pullback-1', setup_type: 'first_pullback', end: 'triggered', reached: 'triggered',
  started_at: at(9, 15), ended_at: at(9, 20), died_at: null, died_bar_t: null, reason: 'traded 1.37 over the 1.35 trigger',
  leg: { t: at(9, 14), high: 1.35, low: 1.2, pct: 0.125 }, after: null, triggered_at: at(9, 17, 4), trigger_price: 1.37,
  setup: { trigger: 1.35, entry: 1.36, stop: 1.31, risk: 0.05, target1: 1.46, armed_bar_t: at(9, 16) },
  score: { outcome: 'target_first', bar_r: 1.629, exit_reason: 'ema' },
};
const ftFadedAtLeg = {
  ...ncplFlag, id: 'NCPL-flat_top_breakout-2', setup_type: 'flat_top_breakout', end: 'faded', reached: 'leg',
  reason: 'new high of day 1.39 on a 12.7% move -- wait for a base under it', after: null,
};
const ftFailingNow = {
  ...ncplFlag, id: 'NCPL-flat_top_breakout-3', setup_type: 'flat_top_breakout', end: null, ended_at: null, ended_by: null,
  reason: 'a base candle closed more than 2% under the 1.43 high', died_at: at(9, 24, 0.2), died_bar_t: at(9, 23),
  leg: { t: at(9, 22), high: 1.43, low: 1.25, pct: 0.144, bars: 0 },
  after: { ...ncplFlag.after, level: 1.43, entry: 1.44, floor: 1.36, first: 'pending', complete: false, trade: null },
};
const wire = { schema_version: 1, symbol: 'NCPL', date: '2026-09-29', generated_at: at(9, 40),
  episodes: [fpTriggered, ncplFlag, ftFadedAtLeg, ftFailingNow],
  counts: { failed: 1, faded: 1, triggered: 1, cut: 0, open: 1 },
  journal: { ok: true, error: null, lines: 7948 }, bars: { ok: true, error: null, count: 230 } };
const past = normalizePastSetups(wire)!;
const byId = (id: string) => past.episodes.find(e => e.id === id) as Episode;

describe('the past setups off the wire', () => {
  it('reads every episode and refuses what is not one', () => {
    expect(past.episodes.map(e => e.id)).toEqual([fpTriggered.id, ncplFlag.id, ftFadedAtLeg.id, ftFailingNow.id]);
    const flag = byId(ncplFlag.id);
    expect(flag.after?.first).toBe('high');
    expect(flag.after?.trade).toMatchObject({ entry: 1.36, stop: 1.31, target: 1.46, outcome: 'open', bar_r: -0.194 });
    const junk = normalizePastSetups({ ...wire, episodes: [...wire.episodes, { id: 'x' }, null,
      { ...ncplFlag, id: 'y', end: 'vanished', after: { ...ncplFlag.after, first: 'sideways' } }] })!;
    expect(junk.episodes).toHaveLength(5);
    expect(junk.episodes[4].end).toBeNull();
    expect(junk.episodes[4].after?.first).toBe('unknown');
    expect(normalizePastSetups({ symbol: 'NCPL' })).toBeNull();
  });
});

describe('what the chart draws, and says', () => {
  it('draws a failed setup from the moment it failed, and never a faded leg', () => {
    expect(endOf(byId(ftFailingNow.id))).toBe('failed');
    expect(drawnPast(past.episodes, []).map(e => e.id)).toEqual([fpTriggered.id, ncplFlag.id, ftFailingNow.id]);
    expect(drawnPast(past.episodes, ['bull_flag']).map(e => e.id)).not.toContain(ncplFlag.id);
    expect([...failingNow(past.episodes)]).toEqual(['flat_top_breakout']);
    expect(pastCounts(drawnPast(past.episodes, []))).toEqual({ failed: 2, faded: 0, triggered: 1 });
  });

  it('names a rule in a few words, and cuts anything else to its first clause', () => {
    expect(shortReason(ncplFlag.reason)).toBe('higher high in the flag');
    expect(shortReason('the flag gave back 61.9% of the pole -- more than 50%')).toBe('gave back too much');
    expect(shortReason("the pole's volume fell (4,102 on its last candle, 5,636 on its first) -- the move is tiring"))
      .toBe('volume faded');
    expect(shortReason('red, 2.7% under the 2.17 open; MACD below zero -- a reclaim now is not a try')).toBe('MACD negative');
    expect(shortReason('something the scanner will say one day (with detail) -- and why')).toBe('something the scanner will say one day');
    expect(shortReason(null)).toBe('');
  });

  it('labels how each ended and what came next', () => {
    expect(pastLabel(byId(ncplFlag.id))).toBe('✕ higher high in the flag · ↗ then broke out');
    expect(pastLabel(byId(fpTriggered.id))).toBe('✓ triggered · target first · +1.6R');
    const neither = { ...byId(fpTriggered.id), score: { outcome: 'open', bar_r: 0, exit_reason: 'bailout' } };
    expect(pastLabel(neither)).toBe('✓ triggered · +0.0R');   // no target or stop yet: the bar exits' R says it
    expect(pastLabel(byId(ftFailingNow.id))).toBe('✕ broke down from the base');   // its 15 minutes are not over
  });

  it('tells the whole story under the pointer', () => {
    const story = pastStory(byId(ncplFlag.id));
    expect(story.title).toBe('Bull flag · failed 09:20');
    expect(story.lines[0]).toBe('The rule it broke: flag candle 2 made a higher high than the candle before it');
    expect(story.lines).toContain('Next 15 min: over 1.35 first at 09:20, before 1.31.');
    expect(story.lines.join(' ')).toContain(
      'The refused trade: entry 1.36, stop 1.31, target 1.46 -- neither the target nor the stop within 15 minutes');
    expect(pastStory(byId(ftFailingNow.id)).lines.join(' ')).toContain('the scanner still shows it failed');
  });

  it('draws the pole and the flag it died in, faint, where they happened', () => {
    const boxes = pastShapes([byId(ncplFlag.id)], { toTime: identity });
    expect(boxes.map(b => [b.t1, b.t2, b.p1, b.p2, b.label])).toEqual([
      [at(9, 15), at(9, 17), 1.27, 1.35, 'POLE +6.3%'],
      [at(9, 18), at(9, 19), 1.31, 1.35, '✕ higher high in the flag · ↗ then broke out'],
    ]);
    expect(boxes.every(b => b.dashed && b.hoverId === pastHoverId(byId(ncplFlag.id)))).toBe(true);
    const fp = pastShapes([byId(fpTriggered.id)], { toTime: identity });
    expect(fp[1]).toMatchObject({ t1: at(9, 15), t2: at(9, 17), p1: 1.31, p2: 1.35 });   // to the trigger's candle
    expect(pastShapes([byId(ncplFlag.id)], { toTime: () => null })).toEqual([]);
  });
});

describe('the 1-minute pane with the past setups', () => {
  const read = normalizeStockRead({
    ...apusReadWire,
    symbol: 'NCPL',
    plan: null,
    setups: [
      { ...apusReadWire.setups[1], setup_type: 'bull_flag', state: 'failed', reason: ncplFlag.reason, forming: null,
        setup: null, leg: { t: at(9, 17), high: 1.35, low: 1.27, pct: 0.063, bars: 3 } },
      { ...apusReadWire.setups[2], setup_type: 'flat_top_breakout', state: 'failed', reason: ftFailingNow.reason,
        forming: null, setup: { trigger: 1.43, entry: 1.44, stop: 1.36, risk: 0.08, target1: 1.6 },
        leg: { t: at(9, 22), high: 1.43, low: 1.25, pct: 0.144, bars: 0 } },
    ],
  }) as StockRead;

  it('says FAILED and why on the pole when a flag failed before it was drawn', () => {
    const { scene } = paneDraw(read, { pane: 'full', layers: { ...LAYERS, past: false }, toTime: identity });
    const pole = scene.boxes.find(b => b.label?.startsWith('POLE'))!;
    expect(pole.label).toBe('POLE +6.3% · FAILED: higher high in the flag');
    expect(pole.hoverId).toBe(laneHoverId('bull_flag'));
  });

  it('draws the past under the live lanes, and a lane failed now as past only', () => {
    const { scene, lines } = paneDraw(read, { pane: 'full', layers: LAYERS, toTime: identity, past: past.episodes });
    const ids = scene.boxes.map(b => b.hoverId);
    expect(ids.indexOf(pastHoverId(byId(ncplFlag.id)))).toBeLessThan(ids.indexOf(laneHoverId('bull_flag')));
    expect(ids).not.toContain(laneHoverId('flat_top_breakout'));        // the failing flat top gives way ...
    expect(scene.boxes.find(b => b.hoverId === pastHoverId(byId(ftFailingNow.id)))?.label)
      .toBe('BASE · ✕ broke down from the base');                        // ... to its past drawing
    expect(scene.segments.map(s => s.label)).not.toContain('FLAT TOP 1.43');
    expect(lines.map(l => l.id)).not.toContain('entry');
    const off = paneDraw(read, { pane: 'full', layers: { ...LAYERS, past: false }, toTime: identity, past: past.episodes });
    expect(off.scene.boxes.some(b => b.hoverId?.startsWith('past:'))).toBe(false);
    expect(off.scene.boxes.some(b => b.hoverId === laneHoverId('flat_top_breakout'))).toBe(true);
  });

  it('tells a live lane its story too', () => {
    const story = laneStory(read.setups[0]);
    expect(story.title).toBe('Bull flag · failed');
    expect(story.lines[0]).toBe(ncplFlag.reason);
  });
});

describe('the pointer over a box', () => {
  function primitive(boxes: { x1: number; x2: number | null; y1: number; y2: number; hoverId?: string }[]) {
    const p = new SetupShapesPrimitive();
    p.px = {
      boxes: boxes.map(b => ({ ...b, b: { hoverId: b.hoverId } as SceneBox })),
      segments: [], vlines: [], tags: [], pins: [],
    };
    return p;
  }

  it('names the top-most box with a story under it', () => {
    const p = primitive([
      { x1: 10, x2: 100, y1: 50, y2: 150, hoverId: 'past:a' },
      { x1: 40, x2: 60, y1: 80, y2: 120, hoverId: 'lane:bull_flag' },
      { x1: 0, x2: null, y1: 0, y2: 400 },                       // a plan zone: no story
    ]);
    expect(p.hitTest(50, 100)).toEqual({ externalId: 'lane:bull_flag', zOrder: 'top' });
    expect(p.hitTest(20, 60)).toEqual({ externalId: 'past:a', zOrder: 'top' });
    expect(p.hitTest(101, 151)).toEqual({ externalId: 'past:a', zOrder: 'top' });   // two pixels of slack
    expect(p.hitTest(300, 300)).toBeNull();
  });
});

describe('the layer switch', () => {
  it('shows past setups unless the operator switched them off, also for a value stored before them', () => {
    expect(parseLayers({ setups: true, levels: true, hidden: [], plan: 'auto' })?.past).toBe(true);
    expect(parseLayers({ past: false })?.past).toBe(false);
  });
});
