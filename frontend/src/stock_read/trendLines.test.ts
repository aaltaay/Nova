import { describe, expect, it } from 'vitest';
import type { Time } from 'lightweight-charts';
import { paneDraw, type DrawOptions } from './chartShapes';
import { normalizeLevelMap, normalizePlanLevels, normalizeTrendLine } from './levelMapNormalize';
import { columnItems, type TrendPx } from './sceneRender';
import { SetupShapesPrimitive } from './SetupShapesPrimitive';
import type { StockReadLayers } from './StockReadContext';
import { centsText, trendHoverId, trendLabel, trendScene, trendStory } from './trendLines';
import type { StockRead } from './types';

// 2026-10-12 09:30 ET and on: one-minute candles.
const T = (m: number) => 1791811800 + 60 * m;

const supportWire = {
  id: 'one_minute:support:1', home: 'one_minute', kind: 'support', dir: 'up', state: 'holding',
  touches: [{ t: T(0), p: 5.0, x: 5.0 }, { t: T(10), p: 5.2, x: 5.19 }, { t: T(20), p: 5.4, x: 5.41 }],
  t1: T(0), p1: 5.0, t2: T(20), p2: 5.4, now_t: T(25), now_p: 5.5, slope: 0.02, band: 0.0275, side: 'below',
  broke: null, retest_t: null, label: 'ascending support · 3 touches', tag: '↗ support',
  note: '3 touches: 09:30, 09:40, 09:50',
};
const brokenWire = {
  ...supportWire, id: 'five_minute:resistance:1', home: 'five_minute', kind: 'resistance', dir: 'down', state: 'broken',
  slope: -0.05, now_p: 5.6, side: 'below', broke: { t: T(20), p: 5.62, close: 5.7 }, retest_t: T(25),
  label: 'descending resistance · 3 touches', tag: '↘ resistance',
};

function readWith(lines: unknown): StockRead {
  const level_map = normalizeLevelMap({ schema_version: 1, price: 5.8, intraday: [], five_minute: [], daily: [], lines });
  return { price: 5.8, level_map, plan: null, setups: [], held: null, levels: { vwap: null }, generated_at: T(26) } as unknown as StockRead;
}

const read = readWith({ one_minute: [supportWire], five_minute: [brokenWire] });
const toTime = (s: number) => s as unknown as Time;

describe('the trend lines on the wire', () => {
  it('keeps a line whole and drops one without its points: a line is never guessed', () => {
    const l = normalizeTrendLine(supportWire);
    expect(l).toMatchObject({ kind: 'support', dir: 'up', state: 'holding', now_p: 5.5, slope: 0.02, side: 'below' });
    expect(l?.touches).toHaveLength(3);
    expect(normalizeTrendLine({ ...supportWire, p2: null })).toBeNull();
    expect(normalizeTrendLine({ ...supportWire, touches: [] })).toBeNull();
    expect(normalizeTrendLine({ ...supportWire, kind: 'channel' })).toBeNull();
    expect(read.level_map?.lines?.five_minute[0].broke).toEqual({ t: T(20), p: 5.62, close: 5.7 });
  });

  it('reads a backend older than the lines as none', () => {
    expect(normalizeLevelMap({ schema_version: 1, intraday: [], daily: [] })?.lines).toBeNull();
  });

  it("carries the plan's line rows", () => {
    const lv = normalizePlanLevels({
      room: { state: 'ok', text: 'No level of today\'s map above the entry' },
      lines: [{ role: 'way', state: 'warn', text: '↘ resistance (5-min) at 5.24 (1.2R) before the target', detail: 'x', line: 'a', price: 5.24 },
        { role: 'elsewhere', state: 'warn', text: 'dropped' }],
    });
    expect(lv?.lines.map(n => [n.role, n.state, n.price])).toEqual([['way', 'warn', 5.24]]);
  });
});

describe('each minute pane draws its own chart\'s lines', () => {
  it('puts the 1-minute lines on the 1-minute pane and the 5-minute lines on the 5-minute pane', () => {
    const one = trendScene(read, 'full', toTime);
    expect(one.map(t => t.hoverId)).toEqual(['trend:one_minute:support:1']);
    expect(one[0]).toMatchObject({ p1: 5.0, p2: 5.4, pEnd: 5.5, slope: 0.02, faded: false, label: '↗ support · 3' });
    expect(one[0].touches).toHaveLength(3);
    const five = trendScene(read, 'map', toTime);
    expect(five).toHaveLength(1);
    expect(five[0].faded).toBe(true);
    expect(five[0].broke).toEqual({ t: T(20), price: 5.62 });
    expect(five[0].color).toMatch(/^rgba\(/);
  });

  it("leaves out a line whose candles the pane does not hold", () => {
    expect(trendScene(read, 'full', s => (s === T(0) ? null : toTime(s)))).toEqual([]);
  });

  it('draws them with the levels, and not on the Full Day pane', () => {
    const layers = { setups: false, levels: true, labels: 'compact', hidden: [], past: false } as unknown as StockReadLayers;
    const o = (pane: DrawOptions['pane'], lv = true): DrawOptions => ({ pane, layers: { ...layers, levels: lv }, toTime });
    expect(paneDraw(read, o('full')).scene.trends).toHaveLength(1);
    expect(paneDraw(read, o('map')).scene.trends).toHaveLength(1);
    expect(paneDraw(read, o('full', false)).scene.trends).toBeUndefined();
    expect(paneDraw(read, o('daily')).scene.trends).toBeUndefined();
  });

  it('names a holding line by its touches and a broken one by its break', () => {
    const [support] = read.level_map!.lines!.one_minute;
    const [broken] = read.level_map!.lines!.five_minute;
    expect(trendLabel(support)).toBe('↗ support · 3');
    expect(trendLabel(broken)).toBe('↘ resistance broke 09:50');
  });
});

describe('the edge column and the pointer', () => {
  const tr = trendScene(read, 'full', toTime)[0];
  const px: TrendPx = { x1: 0, y1: 200, x2: 100, y2: 100, xe: 150, ye: 50, pe: 5.6, rings: [], cross: null, tr };

  it('writes the line\'s name where it runs on the newest candle, with its price when out of view', () => {
    const items = columnItems({ levels: [], words: [], tags: [], trends: [px] }, 400);
    expect(items).toEqual([expect.objectContaining({ y: 50, text: '↗ support · 3', hoverId: 'trend:one_minute:support:1',
      offText: '↗ support · 3 5.60' })]);
  });

  it('names the line under the pointer along its whole length', () => {
    const p = new SetupShapesPrimitive();
    p.px = { boxes: [], segments: [], vlines: [], tags: [], pins: [], labels: 'compact', trends: [px] } as unknown as typeof p.px;
    expect(p.hitTest(50, 150)).toEqual({ externalId: 'trend:one_minute:support:1', zOrder: 'top' });
    expect(p.hitTest(125, 77)).toEqual({ externalId: 'trend:one_minute:support:1', zOrder: 'top' });   // the dashed run-on
    expect(p.hitTest(50, 120)).toBeNull();
  });
});

describe("a line's card", () => {
  it('says what it is, where it runs, how it was drawn, what it means and that it is not measured', () => {
    const [support] = read.level_map!.lines!.one_minute;
    const s = trendStory(trendHoverId(support), read)!;
    expect(s.title).toBe('↗ Ascending support · 5.50');
    expect(s.subtitle).toBe('Support · $0.30 below the price (5.2%)');
    expect(s.sections?.map(x => x.head)).toEqual(['Why it is here', 'What it means', 'Not measured']);
    expect(s.sections?.[0].items[0]).toMatch(/^A rising line through the 1-minute candles' swing lows: they touched it 3 times/);
    expect(s.sections?.[0].items[1]).toContain('A touch may miss it by 2.8c');
    expect(s.sections?.[0].items[2]).toBe('It rises 2c a candle');
    expect(s.sections?.[1].items[1]).toContain('a broken support line often turns into resistance');
  });

  it('tells a broken line by its break, and its retest', () => {
    const [broken] = read.level_map!.lines!.five_minute;
    const s = trendStory(trendHoverId(broken), read)!;
    expect(s.subtitle).toMatch(/^Broke at .*: a candle closed over it$/);
    expect(s.sections?.[1].items.at(-1)).toMatch(/the resistance became support\.$/);
    expect(trendStory('trend:nothing', read)).toBeNull();
  });

  it('says a small move in cents', () => {
    expect([centsText(0.06), centsText(0.021), centsText(-0.0004), centsText(1.2)]).toEqual(['6c', '2.1c', '0.04c', '$1.20']);
  });
});
