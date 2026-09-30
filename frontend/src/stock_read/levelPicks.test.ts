import { describe, expect, it } from 'vitest';
import type { Time } from 'lightweight-charts';
import { paneDraw } from './chartShapes';
import { normalizeLevelMap, normalizePlanLevels } from './levelMapNormalize';
import { dailyPick, levelHoverId, levelNote, levelScene, levelStory, mapPick } from './levelPicks';
import { fitText } from './levelRender';
import type { StockReadLayers } from './StockReadContext';
import type { LevelMap, LevelZone } from './levelTypes';
import { pfsaRead } from './whoTradesFixtures';

/** LGHL at 08:52 ET on 2026-09-30, as the backend's level map would say it (price 6.99). */
function zone(id: string, lo: number, hi: number, side: LevelZone['side'], strength: number, label: string,
  members: [LevelZone['members'][number]['kind'], number, number?][], home: LevelZone['home'] = 'intraday'): LevelZone {
  return {
    id: `${home}:${id}`, lo, hi, price: side === 'above' ? lo : hi, side, strength, label, tag: label.split(' · ')[0], home,
    members: members.map(([kind, price, touches]) => ({
      kind, price, label: kind, touches: touches ?? null, times: [], dates: [], note: null,
    })),
  };
}

const HOD = zone('9.79', 9.79, 9.79, 'above', 3, 'HOD 9.79', [['hod', 9.79]]);
const EIGHT = zone('8.00', 8, 8, 'above', 3, '$8.00', [['whole', 8]]);
const CEILING = zone('7.44', 7.44, 7.5, 'above', 18, '$7.50 · top ×8 · VWAP', [['half', 7.5], ['top', 7.48, 8], ['vwap', 7.44]]);
const T730 = zone('7.30', 7.3, 7.3, 'above', 4, '7.30 · double top', [['top', 7.3, 2]]);
const T724 = zone('7.24', 7.24, 7.24, 'above', 4, '7.24 · double top', [['top', 7.24, 2]]);
const FLOOR = zone('7.00', 7, 7.03, 'at', 15, '$7.00 · bottom ×6', [['whole', 7], ['bottom', 7.01, 6]]);
const B692 = zone('6.92', 6.92, 6.92, 'below', 4, '6.92 · double bottom', [['bottom', 6.92, 2]]);
const B686 = zone('6.86', 6.86, 6.86, 'below', 6, '6.86 · triple bottom', [['bottom', 6.86, 3]]);
const T663 = zone('6.63', 6.63, 6.63, 'below', 4, '6.63 · double top', [['top', 6.63, 2]]);
const B656 = zone('6.56', 6.56, 6.56, 'below', 4, '6.56 · double bottom', [['bottom', 6.56, 2]]);
const HALF = zone('6.50', 6.5, 6.5, 'below', 2, '$6.50', [['half', 6.5]]);
const T621 = zone('6.21', 6.21, 6.21, 'below', 4, '6.21 · double top', [['top', 6.21, 2]]);
const SIX = zone('6.00', 6, 6, 'below', 3, '$6.00', [['whole', 6]]);
const YDAY = zone('5.95', 5.95, 5.95, 'below', 2, '5.95 · yday high', [['yday_high', 5.95]]);
const LOD = zone('4.70', 4.7, 4.7, 'below', 2, 'LOD 4.70', [['lod', 4.7]]);
const INTRADAY = [HOD, EIGHT, CEILING, T730, T724, FLOOR, B692, B686, T663, B656, HALF, T621, SIX, YDAY, LOD];

const D898 = zone('8.98', 8.98, 8.98, 'above', 3, '8.98 · daily highs ×3', [['daily_highs', 8.98, 3]], 'daily');
const D884 = zone('8.84', 8.84, 8.84, 'above', 4, '8.84 · daily highs ×5', [['daily_highs', 8.84, 5]], 'daily');
const D760 = zone('7.60', 7.6, 7.6, 'above', 3, '7.60 · daily highs ×3', [['daily_highs', 7.6, 3]], 'daily');
const D743 = zone('7.43', 7.43, 7.43, 'above', 4, '7.43 · daily lows ×4', [['daily_lows', 7.43, 4]], 'daily');
const D700 = zone('7.00', 7, 7, 'at', 4, '7.00 · daily lows ×5', [['daily_lows', 7, 5]], 'daily');
const D595 = zone('5.95', 5.95, 5.95, 'below', 2, '5.95 · yday high', [['yday_high', 5.95]], 'daily');
const D554 = zone('5.54', 5.54, 5.54, 'below', 2, '5.54 · daily lows ×2', [['daily_lows', 5.54, 2]], 'daily');
const D450 = zone('4.50', 4.5, 4.5, 'below', 2, '4.50 · yday low', [['yday_low', 4.5]], 'daily');
const DAILY = [D898, D884, D760, D743, D700, D595, D554, D450];

const STUDY = {
  source: '5 years of minute bars', round_turn: [24, 16], round_through: [77, 70], round_lost: [68, 63],
  hod_past: [72, 77], top_past: [71, 76], daily_past: [78, 78],
};
const MAP: LevelMap = {
  schema_version: 1, price: 6.99, intraday: INTRADAY, daily: DAILY, daily_sessions: 60, daily_error: null,
  study: STUDY as unknown as LevelMap['study'],
};
const LAYERS: StockReadLayers = { setups: true, levels: true, past: false, labels: 'compact', hidden: [], plan: 'auto' };
const identity = (s: number) => s as Time;

function lghl() {
  return { ...pfsaRead('forming'), symbol: 'LGHL', price: 6.99, plan: null, level_map: MAP };
}

describe('the level map off the wire', () => {
  it('reads zones and the study, and refuses another schema version', () => {
    const wire = { schema_version: 1, price: 6.99, intraday: [CEILING, { id: 'x', lo: 1, hi: 1, price: 1, members: [] }],
      daily: [D700], daily_sessions: 60, daily_error: null, study: STUDY };
    const lm = normalizeLevelMap(wire);
    expect(lm?.intraday.map(z => z.id)).toEqual(['intraday:7.44']);  // a zone with no reason is dropped
    expect(lm?.study?.round_turn).toEqual([24, 16]);
    expect(normalizeLevelMap({ ...wire, schema_version: 2 })).toBeNull();
    expect(normalizeLevelMap(null)).toBeNull();
  });

  it("reads the plan's level notes and needs a Room", () => {
    const notes = normalizePlanLevels({
      room: { state: 'warn', text: '0.9R to HOD 8.77', detail: 'Then $9.00 at 2.2R.', r: 0.88, price: 8.77, trial: 'T7' },
      target: { state: 'ok', text: '8.96 is 4c under $9.00', detail: null }, stop: null, next: null, recent: null,
      between: [{ price: 8.5, lo: 8.5, hi: 8.5, tag: '$8.50', label: '$8.50', round: true, hod: false }],
    });
    expect(notes?.room).toMatchObject({ state: 'warn', r: 0.88, trial: 'T7' });
    expect(notes?.between[0]).toMatchObject({ price: 8.5, round: true });
    expect(normalizePlanLevels({ target: {} })).toBeNull();
  });
});

describe('which levels each chart draws', () => {
  it("draws on the 5-minute the nearest and strongest each side, HOD, LOD, the rounds and yesterday's", () => {
    const pick = mapPick(INTRADAY, 6.99);
    for (const z of [T724, CEILING, T730, FLOOR, B692, B686, T663, HOD, LOD, EIGHT, HALF, SIX, YDAY]) {
      expect(pick.has(z), z.id).toBe(true);
    }
    expect(pick.has(B656)).toBe(false);   // a fourth level under the price: a tick on the axis
    expect(pick.has(T621)).toBe(false);
  });

  it("draws on the Full Day chart the daily levels near the price and yesterday's", () => {
    const pick = dailyPick(DAILY, 6.99);
    expect([...pick].map(z => z.id).sort()).toEqual(
      ['daily:4.50', 'daily:5.54', 'daily:5.95', 'daily:7.00', 'daily:7.43', 'daily:7.60', 'daily:8.84'].sort());
    expect(pick.has(D898)).toBe(false);
  });

  it('turns the picks into lines with labels and the rest into ticks, each naming its card', () => {
    const map = levelScene(lghl(), 'map');
    expect(map.levels).toHaveLength(13);
    expect(map.ticks.map(t => t.hoverId)).toEqual([levelHoverId(B656), levelHoverId(T621)]);
    const ceiling = map.levels.find(l => l.hoverId === levelHoverId(CEILING));
    expect(ceiling).toMatchObject({ lo: 7.44, hi: 7.5, label: '$7.50 · top ×8 · VWAP', width: 2, dash: [7, 4] });
    const daily = levelScene(lghl(), 'daily');
    expect(daily.levels).toHaveLength(7);
    expect(daily.levels.every(l => l.dash.length > 0)).toBe(true);
    expect(levelNote(lghl(), 'map')).toBe("Today's levels (15)");
    expect(levelNote(lghl(), 'daily')).toBe('Daily levels (8)');
  });

  it('draws the maps on the 5-minute and Full Day panes, and none on the 10-second', () => {
    const read = lghl();
    expect(paneDraw(read, { pane: 'map', layers: LAYERS, toTime: identity }).scene.levels).toHaveLength(13);
    const day = paneDraw(read, { pane: 'daily', layers: LAYERS, toTime: identity });
    expect(day.scene.levels).toHaveLength(7);
    expect(day.lines).toEqual([]);
    expect(paneDraw(read, { pane: 'map', layers: { ...LAYERS, levels: false }, toTime: identity }).scene.levels ?? [])
      .toHaveLength(0);
    expect(paneDraw(read, { pane: 'thin', layers: LAYERS, toTime: identity }).scene.levels ?? []).toHaveLength(0);
  });

  it("puts on the 1-minute only the plan's levels between its stop and target that no other line names", () => {
    const read = pfsaRead('near', {
      levels: {
        room: { state: 'warn', text: '0.5R to 4.33', detail: null, r: 0.5, price: 4.33, trial: 'T7' },
        target: null, stop: null, next: null, recent: null,
        between: [
          { price: 4.2, lo: 4.2, hi: 4.2, tag: 'double bottom 4.20', label: '4.20 · double bottom', round: false, hod: false },
          { price: 4.33, lo: 4.33, hi: 4.33, tag: 'double top 4.33', label: '4.33 · double top', round: false, hod: false },
          { price: 4.5, lo: 4.5, hi: 4.5, tag: '$4.50', label: '$4.50', round: true, hod: false },
        ],
      },
    });
    const { lines } = paneDraw(read, { pane: 'full', layers: LAYERS, toTime: identity });
    const between = lines.filter(l => l.id.startsWith('between:'));
    expect(between.map(l => [l.price, l.title])).toEqual([[4.2, 'double bottom 4.20'], [4.33, 'double top 4.33']]);
    expect(between[0].color).toBe('#45c7b8');   // under the entry: support
    expect(between[1].color).toBe('#ff8a70');   // over it: resistance
  });
});

describe("a level's card", () => {
  it('says where it is, what holds it and what the study measured', () => {
    const story = levelStory(levelHoverId(CEILING), lghl());
    expect(story?.title).toBe("Today's map · $7.50 · top ×8 · VWAP (7.44-7.50)");
    expect(story?.lines[0]).toBe('45c above the price (6.4%).');
    expect(story?.lines).toContain('What the data says:');
    expect(story?.lines.some(l => l.startsWith('Before it breaks, a half or whole dollar turned price back 24%'))).toBe(true);
    expect(story?.lines.some(l => l.startsWith('Past a top tested twice or more: 71%'))).toBe(true);
    const floor = levelStory(levelHoverId(FLOOR), lghl());
    expect(floor?.lines[0]).toBe('The price is on it.');
    const daily = levelStory(levelHoverId(D884), lghl());
    expect(daily?.title.startsWith('Full Day chart · ')).toBe(true);
    expect(daily?.lines.some(l => l.includes('Room never counts them'))).toBe(true);
    expect(levelStory('lane:bull_flag', lghl())).toBeNull();
  });
});

describe('a label that does not fit', () => {
  it('drops its last reasons first, then its letters', () => {
    const measure = (t: string) => t.length * 6;
    expect(fitText('$7.50 · top ×8 · VWAP', 200, measure)).toBe('$7.50 · top ×8 · VWAP');
    expect(fitText('$7.50 · top ×8 · VWAP', 100, measure)).toBe('$7.50 · top ×8 …');
    expect(fitText('daily highs ×8', 50, measure)).toBe('daily h…');
  });
});

describe('level labels on a crowded pane', () => {
  it('stack under one another and push back up from the bottom instead of dropping off it', async () => {
    const { stackLabels } = await import('./levelRender');
    expect(stackLabels([10, 12, 50], 200)).toEqual([10, 25, 50]);
    expect(stackLabels([180, 185, 190, 199], 200)).toEqual([148, 163, 178, 193]);
    expect(stackLabels(Array.from({ length: 20 }, () => 100), 60)[0]).toBeNull();
  });
});
