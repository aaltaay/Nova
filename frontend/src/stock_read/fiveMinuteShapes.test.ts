import { describe, expect, it } from 'vitest';
import type { Time } from 'lightweight-charts';
import { paneDraw } from './chartShapes';
import { fiveMinuteOnMinute, fiveMinuteScene, lane5HoverId, leadFive, past5HoverId } from './fiveMinuteShapes';
import { normalizePastSetups, type Episode } from './pastSetups';
import { shapeStory } from './ShapeTip';
import type { StockReadLayers } from './StockReadContext';
import type { SetupLane, StockRead } from './types';
import { pfsaRead } from './whoTradesFixtures';

/** IOVA 2026-09-29 on 5-minute candles (the mockup the operator approved): the 13.80 base near its trigger. */
const ET0 = Date.UTC(2026, 8, 29, 13, 0) / 1000;      // 09:00 ET
const at = (min: number) => ET0 + min * 60;
const LAYERS: StockReadLayers = { setups: true, levels: true, past: true, labels: 'full', hidden: [], plan: 'auto' };
const identity = (s: number) => s as Time;

function lane(setupType: string, state: string, over: Partial<SetupLane> = {}): SetupLane {
  return {
    setup_type: setupType, state, reason: 'broke the 13.80 high -- waiting for a candle that holds', kind: setupType,
    chosen: false, level: 0,
    setup: { trigger: 13.8, entry: 13.81, stop: 13.25, risk: 0.56, target1: 14.94, pullback_bars: 2, armed_bar_t: at(55) },
    forming: null, leg: { t: at(45), high: 13.8, low: 13.24, pct: 0.042, bars: 2 }, last_price: 13.84, distance: null,
    grade: null, phase: null, tape: null, window: { start: '07:00', end: '15:30', state: 'open' }, series: null,
    timeframe: '5m', ...over,
  };
}

/** A read with the built-in 5-minute lanes `setups5` and the setups in play `setups` (the 5-minute flat top). */
function read(setups5: SetupLane[], setups: SetupLane[] = []): StockRead {
  return { ...pfsaRead('forming'), symbol: 'IOVA', plan: null, setups, setups_5m: setups5 };
}

/** The 5-minute flat top: a strategy in play (2026-10-06), its pattern on 5-minute candles. */
function flat5(state: string, over: Partial<SetupLane> = {}): SetupLane {
  return lane('flat_top_5m', state, { level: 1, ...over });
}

const PAST: Episode[] = normalizePastSetups({
  symbol: 'IOVA', date: '2026-09-29', generated_at: at(70), episodes: [{
    id: 'IOVA-flat_top_5m-1', setup_type: 'flat_top_5m', started_at: at(-60), ended_at: at(-40),
    end: 'failed', died_at: at(-40), died_bar_t: at(-45), reason: 'a base candle closed more than 2% under the 12.20 high',
    ended_by: null, reached: 'armed', leg: { t: at(-60), high: 12.2, low: 12.0, pct: 0.03, bars: 2 },
    setup: { trigger: 12.2, entry: 12.21, stop: 12.0, risk: 0.21, target1: 12.63 }, filtered: null,
    triggered_at: null, trigger_price: null, score: null, after: null,
  }],
})!.episodes;

describe('the 5-minute setups on the 5-minute chart', () => {
  it('draws each lane with labels starting 5m, its own hover id, and the lead\'s trigger, stop and target', () => {
    const r = read([lane('bull_flag', 'leg', { setup: null })], [flat5('near')]);
    expect(leadFive([...r.setups_5m, ...r.setups])?.setup_type).toBe('flat_top_5m');
    const f = fiveMinuteScene(r, { toTime: identity, hidden: [], past: PAST });
    expect(f.boxes.every(b => !b.label || b.label.startsWith('5m · '))).toBe(true);
    expect(f.boxes.some(b => b.hoverId === lane5HoverId('flat_top_5m') && b.label?.startsWith('5m · BASE'))).toBe(true);
    // The lead flat top's level is its 5m line's name (below); its segment carries no second one.
    expect(f.segments.some(s => s.price === 13.8 && s.label === null)).toBe(true);
    expect(f.words).toEqual([]);
    // The lead's labels are drawn whole; a faded lane's make room (shown where they fit, else hidden).
    const pole = f.boxes.find(b => b.hoverId === lane5HoverId('bull_flag'));
    expect(pole?.label).toMatch(/^5m · POLE/);
    expect(pole?.shrink).toMatchObject({ short: null, icon: null });
    expect(f.boxes.find(b => b.hoverId === lane5HoverId('flat_top_5m'))?.shrink).toBeUndefined();
    expect(f.lines.map(l => [l.title, l.price, l.style, l.axisLabel])).toEqual([
      ['5m FLAT TOP', 13.8, 'dashed', true], ['5m STOP', 13.25, 'dashed', true], ['5m TARGET', 14.94, 'dashed', true],
    ]);
    // The day's 5-minute setups that ended: their own hover ids, labels starting 5m, on 5-minute candles.
    const past = f.boxes.filter(b => b.hoverId === past5HoverId(PAST[0]));
    expect(past).toHaveLength(1);
    expect(past[0].label).toMatch(/^5m · BASE · /);
    expect(past[0].t1).toBe(at(-60));
    expect(past[0].t2).toBe(at(-45));                     // the 5-minute candle it died on
  });

  it('leaves out a hidden setup; on the 1-minute pane the 5-minute flat top is its level alone until it breaks', () => {
    const r = read([], [flat5('near')]);
    expect(fiveMinuteScene(r, { toTime: identity, hidden: ['flat_top_5m'], past: null }).boxes).toEqual([]);
    const map = paneDraw(r, { pane: 'map', layers: LAYERS, toTime: identity, past5: PAST });
    expect(map.scene.boxes.some(b => b.hoverId === lane5HoverId('flat_top_5m'))).toBe(true);
    expect(map.lines.map(l => l.title)).toEqual(['5m FLAT TOP', '5m STOP', '5m TARGET']);
    expect(paneDraw(r, { pane: 'map', layers: { ...LAYERS, setups: false }, toTime: identity }).scene.boxes).toEqual([]);
    const one = paneDraw(r, { pane: 'full', layers: LAYERS, toTime: identity });
    expect(one.scene.boxes).toEqual([]);                  // no 5-minute base or touches on 1-minute candles
    expect(one.scene.dots ?? []).toEqual([]);
    expect(one.scene.segments.map(g => [g.price, g.label])).toEqual([[13.8, '5m FLAT TOP 13.80']]);   // not the plan's
    expect(one.lines.filter(l => l.id.startsWith('5m-'))).toEqual([]);
  });

  it('puts a chip on the 1-minute chart only for a built-in 5-minute setup armed or near its trigger', () => {
    const near = fiveMinuteOnMinute(read([lane('bull_flag', 'near')]));
    expect(near.chips.map(c => c.text)).toEqual(['5m bull flag · near 13.80']);
    expect(near.chips[0].tip).toMatch(/never propose or trade/);
    expect(near.lines.map(l => [l.title, l.price])).toEqual([['5m bull flag trigger', 13.8]]);
    expect(fiveMinuteOnMinute(read([lane('bull_flag', 'leg', { setup: null })])).chips).toEqual([]);
    expect(fiveMinuteOnMinute(read([lane('first_pullback', 'triggered')])).lines).toEqual([]);
    expect(fiveMinuteOnMinute(read([], [flat5('near')])).chips).toEqual([]);   // a strategy: the legend's own chip
  });

  it('draws the 5-minute flat top\'s break and 1-minute hold on the minute they printed, and in their 5-minute candle', () => {
    const detail = { entry_mode: 'hold', base_low: 13.25, broke_at: at(61) + 20, broke_bar_t: at(61), hold_bar_t: at(63),
      hold_high: 13.92, touches: [[at(45), 13.8], [at(50), 13.78], [at(55), 13.8]] };
    const trig = flat5('triggered', { level: 2, setup: { trigger: 13.8, entry: 13.91, stop: 13.74, risk: 0.17,
      target1: 14.25, pullback_bars: 2, armed_bar_t: at(55), triggered_at: at(64), trigger_price: 13.9, detail } });
    const base = pfsaRead('forming');
    const r: StockRead = { ...read([], [trig]), plan: base.plan && { ...base.plan, source: 'setup', setup_type: 'flat_top_5m' } };
    const one = paneDraw(r, { pane: 'full', layers: LAYERS, toTime: identity, highAt: () => 13.86 });
    const hold = one.scene.boxes.find(b => b.label === 'hold');
    expect(hold && [hold.t1, hold.t2, hold.p1, hold.p2]).toEqual([at(63), at(63), 13.74, 13.92]);
    expect(one.scene.marks?.map(m => [m.t, m.label])).toEqual([[at(61), 'break']]);
    expect(one.scene.words?.map(w => w.text)).toEqual(['5m FLAT TOP 13.80']);
    // On the 5-minute pane both fell in the 07:00 candle: one label over the break's triangle says both, and the
    // hold's box, on that candle, goes unlabelled (its label would cover the triangle).
    const map = paneDraw(r, { pane: 'map', layers: LAYERS, toTime: identity, highAt: () => 13.86 });
    const hold5 = map.scene.boxes.find(b => b.t1 === at(60) && b.p2 === 13.92);
    expect(hold5 && [hold5.t2, hold5.p1, hold5.label]).toEqual([at(60), 13.74, null]);
    expect(map.scene.marks?.map(m => [m.t, m.label])).toEqual([[at(60), '5m · break · 1m hold']]);
    // A hold in a later 5-minute candle than the break keeps its own label.
    const later = { ...trig, setup: { ...trig.setup!, detail: { ...detail, hold_bar_t: at(65) } } };
    const apart = paneDraw({ ...r, setups: [later] }, { pane: 'map', layers: LAYERS, toTime: identity, highAt: () => 13.86 });
    expect(apart.scene.boxes.find(b => b.label === '5m · 1m hold')?.t1).toBe(at(65));
    expect(apart.scene.marks?.map(m => m.label)).toEqual(['5m · break']);
  });

  it('names a built-in 5-minute lane\'s card as 5-minute, and the 5-minute flat top\'s as itself', () => {
    const r = read([lane('bull_flag', 'near')], [flat5('near')]);
    expect(shapeStory(lane5HoverId('bull_flag'), r, null, PAST)?.title).toMatch(/^5-minute · /);
    expect(shapeStory(lane5HoverId('flat_top_5m'), r, null, PAST)?.title).toBe('5-minute flat top 13.80 · near');
    expect(shapeStory(past5HoverId(PAST[0]), r, null, PAST)?.title).toMatch(/^5-minute flat top · failed/);
    expect(shapeStory('lane5:red_to_green', r, null, PAST)).toBeNull();
  });
});
