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

function read(setups5: SetupLane[]): StockRead {
  return { ...pfsaRead('forming'), symbol: 'IOVA', plan: null, setups: [], setups_5m: setups5 };
}

const PAST: Episode[] = normalizePastSetups({
  symbol: 'IOVA', date: '2026-09-29', generated_at: at(70), episodes: [{
    id: 'IOVA-flat_top_breakout-1', setup_type: 'flat_top_breakout', started_at: at(-60), ended_at: at(-40),
    end: 'failed', died_at: at(-40), died_bar_t: at(-45), reason: 'a base candle closed more than 2% under the 12.20 high',
    ended_by: null, reached: 'armed', leg: { t: at(-60), high: 12.2, low: 12.0, pct: 0.03, bars: 2 },
    setup: { trigger: 12.2, entry: 12.21, stop: 12.0, risk: 0.21, target1: 12.63 }, filtered: null,
    triggered_at: null, trigger_price: null, score: null, after: null,
  }],
})!.episodes;

describe('the 5-minute setups on the 5-minute chart', () => {
  it('draws each lane with labels starting 5m, its own hover id, and the lead\'s trigger, stop and target', () => {
    const r = read([lane('flat_top_breakout', 'near'), lane('bull_flag', 'leg', { setup: null })]);
    expect(leadFive(r.setups_5m)?.setup_type).toBe('flat_top_breakout');
    const f = fiveMinuteScene(r, { toTime: identity, hidden: [], past: PAST });
    expect(f.boxes.every(b => !b.label || b.label.startsWith('5m · '))).toBe(true);
    expect(f.boxes.some(b => b.hoverId === lane5HoverId('flat_top_breakout') && b.label?.startsWith('5m · BASE'))).toBe(true);
    expect(f.segments.map(s => s.label)).toContain('5m · FLAT TOP 13.80');
    // The lead's labels are drawn whole; a faded lane's make room (shown where they fit, else hidden).
    const pole = f.boxes.find(b => b.hoverId === lane5HoverId('bull_flag'));
    expect(pole?.label).toMatch(/^5m · POLE/);
    expect(pole?.shrink).toMatchObject({ short: null, icon: null });
    expect(f.boxes.find(b => b.hoverId === lane5HoverId('flat_top_breakout'))?.shrink).toBeUndefined();
    expect(f.lines.map(l => [l.title, l.price, l.style, l.axisLabel])).toEqual([
      ['5m TRIGGER', 13.8, 'dashed', true], ['5m STOP', 13.25, 'dashed', true], ['5m TARGET', 14.94, 'dashed', true],
    ]);
    // The day's 5-minute setups that ended: their own hover ids, labels starting 5m, on 5-minute candles.
    const past = f.boxes.filter(b => b.hoverId === past5HoverId(PAST[0]));
    expect(past).toHaveLength(1);
    expect(past[0].label).toMatch(/^5m · BASE · /);
    expect(past[0].t1).toBe(at(-60));
    expect(past[0].t2).toBe(at(-45));                     // the 5-minute candle it died on
  });

  it('leaves out a hidden setup and draws nothing of the 5-minute lanes on the 1-minute pane but their trigger', () => {
    const r = read([lane('flat_top_breakout', 'near')]);
    expect(fiveMinuteScene(r, { toTime: identity, hidden: ['flat_top_breakout'], past: null }).boxes).toEqual([]);
    const map = paneDraw(r, { pane: 'map', layers: LAYERS, toTime: identity, past5: PAST });
    expect(map.scene.boxes.some(b => b.hoverId === lane5HoverId('flat_top_breakout'))).toBe(true);
    expect(map.lines.map(l => l.title)).toEqual(['5m TRIGGER', '5m STOP', '5m TARGET']);
    expect(paneDraw(r, { pane: 'map', layers: { ...LAYERS, setups: false }, toTime: identity }).scene.boxes).toEqual([]);
    const one = paneDraw(r, { pane: 'full', layers: LAYERS, toTime: identity });
    expect(one.scene.boxes.some(b => b.hoverId?.startsWith('lane5:'))).toBe(false);
    expect(one.lines.filter(l => l.id.startsWith('5m-')).map(l => [l.title, l.price])).toEqual([['5m flat top trigger', 13.8]]);
  });

  it('puts a chip on the 1-minute chart only for a 5-minute setup armed or near its trigger', () => {
    const near = fiveMinuteOnMinute(read([lane('flat_top_breakout', 'near')]));
    expect(near.chips.map(c => c.text)).toEqual(['5m flat top · near 13.80']);
    expect(near.chips[0].tip).toMatch(/never propose or trade/);
    expect(fiveMinuteOnMinute(read([lane('bull_flag', 'leg', { setup: null })])).chips).toEqual([]);
    expect(fiveMinuteOnMinute(read([lane('first_pullback', 'triggered')])).lines).toEqual([]);
  });

  it('names a 5-minute lane\'s and setup\'s card as 5-minute', () => {
    const r = read([lane('flat_top_breakout', 'near')]);
    expect(shapeStory(lane5HoverId('flat_top_breakout'), r, null, PAST)?.title).toMatch(/^5-minute · /);
    expect(shapeStory(past5HoverId(PAST[0]), r, null, PAST)?.title).toMatch(/^5-minute · /);
    expect(shapeStory('lane5:red_to_green', r, null, PAST)).toBeNull();
  });
});
