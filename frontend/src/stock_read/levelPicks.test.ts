import { describe, expect, it } from 'vitest';
import type { Time } from 'lightweight-charts';
import { paneDraw } from './chartShapes';
import { normalizeLevelMap, normalizePlanLevels } from './levelMapNormalize';
import {
  dailyPick, levelHoverId, levelNote, levelScene, levelStory, mapPick, minuteScene,
} from './levelPicks';
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

/** The same morning read from 5-minute candles: fewer, wider tops (two 1-minute tops inside one 5-minute
 * candle are one top here). */
const F_HOD = zone('9.79', 9.79, 9.79, 'above', 3, 'HOD 9.79', [['hod', 9.79]], 'five_minute');
const F_800 = zone('8.00', 8, 8, 'above', 7, '$8.00 · double top', [['whole', 8], ['top', 8, 2]], 'five_minute');
const F_770 = zone('7.70', 7.7, 7.7, 'above', 4, '7.70 · double top', [['top', 7.7, 2]], 'five_minute');
const F_CEIL = zone('7.48', 7.48, 7.5, 'above', 8, '$7.50 · double top', [['half', 7.5], ['top', 7.48, 2]], 'five_minute');
const F_730 = zone('7.30', 7.3, 7.3, 'above', 4, '7.30 · double top', [['top', 7.3, 2]], 'five_minute');
const F_FLOOR = zone('7.00', 7, 7.01, 'at', 9, '$7.00 · triple bottom', [['whole', 7], ['bottom', 7.01, 3]], 'five_minute');
const F_686 = zone('6.86', 6.86, 6.86, 'below', 4, '6.86 · double bottom', [['bottom', 6.86, 2]], 'five_minute');
const F_PMH = zone('6.70', 6.7, 6.7, 'below', 2, '6.70 · PMH', [['pmh', 6.7]], 'five_minute');
const F_650 = zone('6.50', 6.5, 6.5, 'below', 6, '$6.50 · double bottom', [['half', 6.5], ['bottom', 6.5, 2]], 'five_minute');
const F_640 = zone('6.40', 6.4, 6.4, 'below', 4, '6.40 · double bottom', [['bottom', 6.4, 2]], 'five_minute');
const F_LOD = zone('4.70', 4.7, 4.7, 'below', 2, 'LOD 4.70', [['lod', 4.7]], 'five_minute');
const FIVE = [F_HOD, F_800, F_770, F_CEIL, F_730, F_FLOOR, F_686, F_PMH, F_650, F_640, F_LOD];

const STUDY = {
  source: '5 years of minute bars', round_turn: [24, 16], round_through: [77, 70], round_lost: [68, 63],
  hod_past: [72, 77], top_past: [71, 76], daily_past: [78, 78],
};
const MAP: LevelMap = {
  schema_version: 1, price: 6.99, intraday: INTRADAY, five_minute: FIVE, daily: DAILY, daily_sessions: 60, daily_error: null,
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
    // A backend older than the 5-minute map sends none: unknown, never the 1-minute map in its place.
    expect(lm?.five_minute).toBeNull();
    const five = normalizeLevelMap({ ...wire, five_minute: [F_CEIL] })?.five_minute;
    expect(five?.map(z => [z.id, z.home])).toEqual([['five_minute:7.48', 'five_minute']]);
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
  it('draws on the 5-minute its own map: the nearest and strongest each side, the zone the price is on, HOD, LOD', () => {
    const pick = mapPick(FIVE, 6.99);
    for (const z of [F_730, F_CEIL, F_770, F_FLOOR, F_686, F_650, F_640, F_HOD, F_LOD]) {
      expect(pick.has(z), z.id).toBe(true);
    }
    expect(pick.has(F_800)).toBe(false);  // past 12% of the price: a tick on the axis
    expect(pick.has(F_PMH)).toBe(false);  // a fourth level under the price: a tick
  });

  it("draws on the Full Day chart the daily levels near the price and yesterday's", () => {
    const pick = dailyPick(DAILY, 6.99);
    expect([...pick].map(z => z.id).sort()).toEqual(
      ['daily:4.50', 'daily:5.54', 'daily:5.95', 'daily:7.00', 'daily:7.43', 'daily:7.60', 'daily:8.84'].sort());
    expect(pick.has(D898)).toBe(false);
  });

  it('turns the picks into lines with labels and the rest into ticks, each naming its card', () => {
    const map = levelScene(lghl(), 'map');
    expect(map.levels).toHaveLength(9);
    expect(map.ticks.map(t => t.hoverId)).toEqual([levelHoverId(F_800), levelHoverId(F_PMH)]);
    const ceiling = map.levels.find(l => l.hoverId === levelHoverId(F_CEIL));
    expect(ceiling).toMatchObject({ lo: 7.48, hi: 7.5, label: '$7.50 · double top', width: 2, dash: [7, 4] });
    expect(map.levels.find(l => l.hoverId === levelHoverId(F_730))?.label).toBe('7.30 · double top');
    expect(map.levels.find(l => l.hoverId === levelHoverId(F_PMH))).toBeUndefined();
    // Nothing of the 1-minute map reaches the 5-minute pane.
    expect(map.levels.some(l => l.hoverId?.startsWith('level:intraday:'))).toBe(false);
    const daily = levelScene(lghl(), 'daily');
    expect(daily.levels).toHaveLength(7);
    expect(daily.levels.every(l => l.dash.length > 0)).toBe(true);
    expect(levelNote(lghl(), 'map')).toBe('5-minute levels (11)');
    const older = { ...lghl(), level_map: { ...MAP, five_minute: null } };
    expect(levelScene(older, 'map').levels).toEqual([]);
    expect(levelNote(older, 'map')).toMatch(/older than this desk/);
    expect(levelNote(lghl(), 'daily')).toBe('Daily levels (8)');
  });

  it('draws the maps on the 5-minute and Full Day panes, and none on the 10-second', () => {
    const read = lghl();
    expect(paneDraw(read, { pane: 'map', layers: LAYERS, toTime: identity }).scene.levels).toHaveLength(9);
    const day = paneDraw(read, { pane: 'daily', layers: LAYERS, toTime: identity });
    expect(day.scene.levels).toHaveLength(7);
    expect(day.lines).toEqual([]);
    expect(paneDraw(read, { pane: 'map', layers: { ...LAYERS, levels: false }, toTime: identity }).scene.levels ?? [])
      .toHaveLength(0);
    expect(paneDraw(read, { pane: 'thin', layers: LAYERS, toTime: identity }).scene.levels ?? []).toHaveLength(0);
  });

  it('puts on the 1-minute the levels its own candles made near the price, each with a label and a card', () => {
    const read = { ...lghl(), level_map: { ...MAP, intraday: [{ ...HOD, members: [...HOD.members,
      { kind: 'top' as const, price: 9.79, label: 'double top', touches: 2, times: [], dates: [], note: null }] },
    ...INTRADAY.slice(1)] } };
    const m = minuteScene(read);
    // The HOD and what its 1-minute candles made of it; the zone the price is on (FLOOR); the nearest top
    // over it (T724) and bottom under it (B692); the nearest round each side ($7.50 in CEILING, $6.50).
    expect(m.levels.map(l => l.label)).toEqual([
      '9.79 · HOD · double top', '$7.50 · VWAP · top ×8', '7.24 · double top', '$7.00 · bottom ×6',
      '6.92 · double bottom', '$6.50',
    ]);
    expect(m.levels.every(l => l.hoverId?.startsWith('level:intraday:'))).toBe(true);
    expect(m.ticks).toEqual([]);
    const { scene, lines } = paneDraw(read, { pane: 'full', layers: LAYERS, toTime: identity });
    expect(scene.levels?.map(l => l.label)).toEqual(m.levels.map(l => l.label));
    // No bare price lines: lightweight-charts shows a line's title only beside an axis label.
    expect(lines.filter(l => !['entry', 'stop', 'target'].includes(l.id))).toEqual([]);
    // The premarket high is the 5-minute pane's; yesterday's high the Full Day's.
    expect(scene.levels?.some(l => /PMH|Yest/.test(l.label ?? ''))).toBe(false);
  });

  it("puts on the 1-minute the plan's levels between its stop and target", () => {
    const Z420 = zone('4.20', 4.2, 4.2, 'below', 4, '4.20 · double bottom', [['bottom', 4.2, 2]]);
    const Z433 = zone('4.33', 4.33, 4.33, 'above', 4, '4.33 · double top', [['top', 4.33, 2]]);
    const Z480 = zone('4.80', 4.8, 4.8, 'above', 4, '4.80 · double top', [['top', 4.8, 2]]);
    const read = { ...pfsaRead('near', {
      levels: {
        room: { state: 'warn', text: '0.5R to 4.33', detail: null, r: 0.5, price: 4.33, trial: 'T7' },
        target: null, stop: null, next: null, recent: null,
        between: [
          { price: 4.2, lo: 4.2, hi: 4.2, tag: 'double bottom 4.20', label: '4.20 · double bottom', round: false, hod: false },
          { price: 4.33, lo: 4.33, hi: 4.33, tag: 'double top 4.33', label: '4.33 · double top', round: false, hod: false },
        ],
      },
    }), level_map: { ...MAP, price: 4.26, intraday: [Z480, Z433, Z420] } };
    const labels = minuteScene(read).levels.map(l => [l.label, l.color]);
    expect(labels).toEqual([['4.33 · double top', '#ff8a70'], ['4.20 · double bottom', '#45c7b8']]);
  });
});

describe("a level's card", () => {
  it('says in plain words what it is, how far, why it is there and what usually happens', () => {
    const story = levelStory(levelHoverId(CEILING), lghl());
    expect(story?.title).toBe('$7.50  7.44–7.50');
    expect(story?.subtitle).toBe('Resistance · $0.45 above the price (6.4%)');
    expect(story?.color).toBe('#f59e0b');
    expect(story?.sections?.[0]).toEqual({ head: 'Why it is here', items: [
      'Half dollar: a round price traders watch', 'Price turned down here 8 times on 1-minute candles',
      "VWAP: the day's average price",
    ] });
    expect(story?.sections?.[1].head).toBe('What usually happens');
    expect(story?.sections?.[1].items[0]).toMatch(/^Round prices often stall a move the first time/);
    expect(story?.lines).toEqual([]);
    // A 5-minute level names the candles its tops were counted on.
    expect(levelStory(levelHoverId(F_730), lghl())?.sections?.[0].items)
      .toEqual(['Price turned down here 2 times on 5-minute candles']);
    const floor = levelStory(levelHoverId(FLOOR), lghl());
    expect(floor?.subtitle).toBe('The price is on it now');
    const daily = levelStory(levelHoverId(D884), lghl());
    expect(daily?.sections?.[0].items).toEqual(['A daily high on 5 days']);
    expect(daily?.sections?.[1].items).toEqual(["Old daily highs did not slow gappers in Nova's study."]);
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
