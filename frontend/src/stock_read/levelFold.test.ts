import { describe, expect, it } from 'vitest';
import type { Time } from 'lightweight-charts';
import { EDGE_PRIORITY } from '../chart';
import type { PriceLineSpec } from './chartShapes';
import { foldColumn, foldedStory, foldHoverId, foldParts, foldSegments } from './levelFold';
import { bands, levelScene } from './levelPicks';
import type { LevelPx } from './levelRender';
import type { LevelMap, LevelZone } from './levelTypes';
import { columnItems, shownLevels, type TrendPx } from './sceneRender';
import type { Scene, SceneTrend, SceneWord } from './sceneTypes';
import type { ShapeStory } from './ShapeTip';
import { pfsaRead } from './whoTradesFixtures';

/** The operator's 1-minute chart on 2026-10-13 at 09:19 ET (report: "there are way too many lines here"): price 4.04, a
 * Gap and Go forming with entry 4.20, stop 4.03, T1 4.40 and T2 4.49. */
function zone(lo: number, hi: number, side: LevelZone['side'], strength: number,
  members: [LevelZone['members'][number]['kind'], number, number?][], home: LevelZone['home'] = 'intraday'): LevelZone {
  const id = `${home}:${lo.toFixed(2)}`;
  return {
    id, lo, hi, price: side === 'above' ? lo : hi, side, strength, label: id, tag: lo.toFixed(2), home,
    members: members.map(([kind, price, touches]) => ({
      kind, price, label: kind, touches: touches ?? null, times: [], dates: [], note: null,
    })),
  };
}

const TOP_412 = zone(4.12, 4.12, 'above', 10, [['top', 4.12, 5]], 'five_minute');
const TOP_409 = zone(4.09, 4.09, 'above', 6, [['top', 4.09, 3]], 'five_minute');
const FAR_450 = zone(4.48, 4.5, 'above', 6, [['half', 4.5], ['bottom', 4.48, 2]], 'five_minute');
const UNDER = zone(4.0, 4.0, 'below', 3, [['whole', 4.0]], 'five_minute');
const UNDER_399 = zone(3.99, 3.99, 'below', 4, [['bottom', 3.99, 2]], 'five_minute');

/** A price axis 400 px tall from 3.80 (bottom) to 4.60 (top). */
const y = (p: number) => 400 - ((p - 3.8) / 0.8) * 400;

function level(lo: number, hi: number, label: string, foldName: string, hoverId: string, priority = EDGE_PRIORITY.level):
  LevelPx {
  const price = lo;
  return { y: y(price), y1: y(hi), y2: y(lo), l: { lo, hi, price, color: '#ff8a70', dash: [], width: 1, label, hoverId,
    foldName, priority } };
}

function word(id: string, text: string, price: number, priority: number, absorbs: boolean): { y: number; value: number;
  w: SceneWord } {
  return { y: y(price), value: price, w: { id, text, color: '#fff', priority, price, series: null, valueWhenOff: false,
    style: 'plain', absorbs } };
}

function trend(label: string, pe: number, o: Partial<SceneTrend> = {}): TrendPx {
  const tr: SceneTrend = {
    t1: 1 as Time, p1: 4.3, t2: 2 as Time, p2: 4.2, tEnd: 3 as Time, pEnd: pe, slope: -0.003, color: '#ff9f43',
    faded: false, touches: [], broke: null, label, labelColor: '#ff9f43', hoverId: `trend:${label}`,
    priority: EDGE_PRIORITY.trendLine, foldName: '↘', ...o,
  };
  return { x1: 0, y1: y(4.3), x2: 10, y2: y(4.2), xe: 20, ye: y(pe), pe, rings: [], cross: null, tr };
}

const PLAN = EDGE_PRIORITY.planLine;

describe('one label per price (operator report 2026-10-13)', () => {
  it('makes tops 3c apart on one side of the price one band, and keeps a level 1.5% away its own', () => {
    expect(bands([TOP_412, TOP_409, FAR_450, UNDER, UNDER_399]).map(g => g.map(z => z.lo)))
      .toEqual([[3.99, 4.0], [4.09, 4.12], [4.48]]);
    // A support and a resistance either side of the price stay two, however near.
    const at = zone(4.05, 4.05, 'above', 4, [['top', 4.05, 2]]);
    const under = zone(4.03, 4.03, 'below', 4, [['bottom', 4.03, 2]]);
    expect(bands([at, under])).toHaveLength(2);
  });

  it('draws the band as one line and one label, its card each zone\'s', () => {
    const map: LevelMap = {
      schema_version: 1, price: 4.04, rounds: null, intraday: [], five_minute: [FAR_450, TOP_412, TOP_409],
      daily: [], daily_sessions: 0, daily_error: null, study: null as unknown as LevelMap['study'],
    };
    const read = { ...pfsaRead('forming'), price: 4.04, plan: null, level_map: map };
    const { levels } = levelScene(read, 'map');
    const band = levels.find(l => l.lo === 4.09)!;
    expect(band).toMatchObject({ hi: 4.12, price: 4.09, label: '4.09–4.12 · top ×8', foldName: 'top ×8' });
    expect(foldParts(band.hoverId!)).toEqual({ title: '4.09–4.12 · top ×8',
      ids: ['level:five_minute:4.09', 'level:five_minute:4.12'] });
    expect(levels.find(l => l.lo === 4.48)).toMatchObject({ label: '$4.50 · double bottom', foldName: '$4.50' });
  });

  it('folds each level into the line at its price: 15 names on that chart down to 7', () => {
    const px = {
      levels: [
        level(4.09, 4.12, '4.09–4.12 · top ×8', 'top ×8', 'fold|4.09–4.12 · top ×8|level:a|level:b'),
        level(4.5, 4.5, '$4.50 · double bottom', '$4.50', 'level:4.50'),
        level(4.36, 4.36, '4.36 · VWAP', 'VWAP', 'level:4.36'),
        level(4.0, 4.0, '$4.00', '$4.00', 'level:4.00'),
      ],
      words: [
        word('strategy:target2', 'T2 4.49', 4.49, PLAN, true),
        word('strategy:target', 'T1 4.40', 4.4, PLAN, true),
        word('strategy:entry', 'entry 4.20 · PMH', 4.2, PLAN, true),
        word('strategy:stop', 'stop 4.03', 4.03, PLAN, true),
        word('vwap', 'VWAP $4.36', 4.36, EDGE_PRIORITY.vwap, true),
        word('ema9', '9 EMA', 4.05, EDGE_PRIORITY.ema + 2, false),
      ],
      tags: [],
      trends: [
        trend('↘ resistance · 4', 4.15),
        // A broken line has no name at the edge; a line past the stop has no tag out of view.
        trend('', 4.1, { faded: true }),
        trend('↗ support · 5', 3.73, { offTag: false, foldName: '↗' }),
      ],
    };
    const items = columnItems(px, 400);
    expect(items.filter(i => i.y >= 0 && i.y <= 400).map(i => i.text)).toEqual([
      '4.09–4.12 · top ×8 · ↘',
      'T2 4.49 · $4.50',
      'T1 4.40',
      'entry 4.20 · PMH',
      'stop 4.03 · $4.00',
      'VWAP $4.36',
      '9 EMA',
    ]);
    expect(items.some(i => i.offText !== null && i.offText.includes('support'))).toBe(false);
    const byText = (t: string) => items.find(i => i.text === t)!;
    // Every folded name opens its card from the label that took it.
    expect(foldParts(byText('4.09–4.12 · top ×8 · ↘').hoverId!)?.ids)
      .toEqual(['level:a', 'level:b', 'trend:↘ resistance · 4']);
    expect(foldParts(byText('stop 4.03 · $4.00').hoverId!)).toEqual({ title: 'stop 4.03', ids: ['level:4.00'] });
    expect(foldParts(byText('VWAP $4.36').hoverId!)).toEqual({ title: 'VWAP $4.36', ids: ['level:4.36'] });
    expect(byText('T1 4.40').hoverId).toBeNull();
    // A level that folded draws no line of its own: the word it joined stands for it.
    expect(shownLevels(px, 400).map(l => l.l.label)).toEqual(['4.09–4.12 · top ×8']);
  });

  it('never folds the plan\'s lines into each other, nor a word out of view', () => {
    const items = foldColumn([
      { y: 100, text: 'entry 20.10', color: '', style: 'plain', priority: PLAN, hoverId: null, offText: null,
        price: 20.1, absorbs: true },
      { y: 104, text: 'stop 19.95', color: '', style: 'plain', priority: PLAN, hoverId: null, offText: null,
        price: 19.95, absorbs: true },
      { y: -5, text: 'HOD 20.12', color: '', style: 'plain', priority: EDGE_PRIORITY.highOfDay, hoverId: 'level:h',
        offText: 'HOD 20.12', price: 20.12, foldName: 'HOD', absorbs: true },
    ], 400);
    expect(items.map(i => i.text)).toEqual(['entry 20.10', 'stop 19.95', 'HOD 20.12']);
  });

  it("makes the gap and go's premarket high a cent under the entry the entry's word", () => {
    const scene: Scene = {
      boxes: [], vlines: [], edgeTags: [], pins: [], keepInView: null, labels: 'compact',
      segments: [
        { t1: 1 as Time, price: 4.19, color: '#f0c040', dashed: true, label: 'PMH 4.19', name: 'PMH' },
        { t1: 1 as Time, price: 3.5, color: '#f0c040', dashed: true, label: 'OPEN 3.50', name: 'OPEN' },
        { t1: 1 as Time, price: 4.2, color: '#f0c040', dashed: true, label: 'then: trigger 4.20' },
      ],
      words: [
        { id: 'strategy:entry', text: 'entry 4.20', color: '', priority: PLAN, price: 4.2, series: null,
          valueWhenOff: false, style: 'plain', absorbs: true },
      ],
    };
    const out = foldSegments(scene, []);
    expect(out.scene.words?.map(w => w.text)).toEqual(['entry 4.20 · PMH']);
    expect(out.scene.segments.map(s => s.label)).toEqual(['OPEN 3.50', 'then: trigger 4.20']);
    // An unboxed plan's line names itself in the column with its title.
    const line: PriceLineSpec = { id: 'entry', price: 4.2, color: '', width: 2, style: 'dashed', title: 'ENTRY',
      axisLabel: true };
    const lined = foldSegments({ ...scene, words: [] }, [line]);
    expect(lined.lines[0].title).toBe('ENTRY · PMH');
    expect(lined.scene.segments).toHaveLength(2);
  });

  it("opens one card with each part's story, a shared sentence once", () => {
    const story = (title: string, why: string): ShapeStory => ({
      title, subtitle: `Resistance · ${title}`, lines: [], color: '#ff8a70',
      sections: [{ head: 'Why it is here', items: [why] },
        { head: 'What usually happens', items: ['It slows price a little.'] }],
    });
    const stories: Record<string, ShapeStory> = {
      'level:a': story('4.09', 'Price turned down here 3 times'),
      'level:b': story('4.12', 'Price turned down here 5 times'),
    };
    const id = foldHoverId('4.09–4.12 · top ×8', ['level:a', 'level:b', 'level:gone'])!;
    expect(foldedStory(id, part => stories[part] ?? null)).toEqual({
      title: '4.09–4.12 · top ×8', color: '#ff8a70', lines: [],
      sections: [
        { head: '4.09', items: ['Resistance · 4.09', 'Price turned down here 3 times'] },
        { head: '4.12', items: ['Resistance · 4.12', 'Price turned down here 5 times'] },
        { head: 'What usually happens', items: ['It slows price a little.'] },
      ],
    });
    expect(foldedStory('level:a', () => null)).toBeNull();
    // A fold of a fold names each part once.
    expect(foldParts(foldHoverId('stop 4.03', [id, 'level:a'])!)?.ids).toEqual(['level:a', 'level:b', 'level:gone']);
  });
});
