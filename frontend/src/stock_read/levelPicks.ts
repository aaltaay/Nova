/**
 * Which of the day's levels each chart draws (ADR 036 amendment 2026-09-30, operator ask: "we can
 * identify major resistance/support levels ... sometimes we have to look at the very obvious
 * resistance/support levels"). Pure. Each chart carries only the levels its own candles show
 * (operator report 2026-09-30: "why does it say it's a double top when, on the graph, we only see one
 * top? ... Every chart has special needs and special powers ... no reason to have duplicate
 * information"):
 *
 * - **5-minute** (`map`): the day read from 5-minute candles (`level_map.five_minute`). Per side, the
 *   nearest zone and the strongest others within 12% of the price (three in all); the zone the price is
 *   on; the high and low of day. Each gets a line and a label at the right edge.
 * - **Full Day** (`daily`): the daily map, the same way within 40%, with yesterday's levels.
 * - **1-minute** (`minuteScene`): from today's 1-minute map, the high of day, the zone the price is on,
 *   the nearest top or bottom its 1-minute candles made above and below the price, the nearest round
 *   number each side (the stock's own scale, `level_map.rounds`: half and whole dollars up to $25, $5 and
 *   $10 on a $225 stock), and the plan's levels between its stop and target. No axis ticks.
 *
 * Picked zones on one side of the price within `LEVEL_FOLD_PCT` of each other are one band with one label
 * (operator report 2026-10-13, "there are way too many lines here": a triple top 3c under a top x5 was two lines and
 * two labels), its card each zone's (`levelFold.ts`). Every other zone of a map is a short tick on the price axis. A
 * label or a tick names its hover card (`level:<zone id>`), whose story is `levelZone.levelStory`; a zone's colour and
 * words are `levelZone.ts`. Nothing here is estimated: every price is the backend's level map.
 */
import {
  LEVEL_DAILY_WINDOW_PCT,
  LEVEL_FOLD_PCT,
  LEVEL_MAP_WINDOW_PCT,
  LEVEL_PER_SIDE,
  LEVEL_ROUND_LINE_ALPHA,
} from './constants';
import { EDGE_PRIORITY } from '../chart';
import { foldHoverId, near } from './levelFold';
import type { SceneLevel, SceneTick } from './levelRender';
import type { LevelZone } from './levelTypes';
import {
  bandLabel, foldWord, has, isDaily, isRound, isYesterday, levelHoverId, roundOnly, shortLabel, YESTERDAY, zoneColor,
} from './levelZone';
import type { SceneEdgeTag } from './sceneTypes';
import type { StockRead } from './types';

export type LevelPane = 'map' | 'daily';

/** What candles make: a top or a bottom tested twice or more. */
const CANDLE = new Set(['top', 'bottom']);
/** A zone this strong gets the heavier line. */
const STRONG = 8;
const DASH = { yesterday: [1, 3], daily: [4, 3], solid: [] as number[] };

function dist(z: LevelZone, price: number): number {
  return Math.abs(z.price - price) / price;
}

/** Per side, the nearest zone and the strongest others within `window` of the price: `n` in all. */
function pickSide(zones: LevelZone[], price: number, side: 'above' | 'below', window: number, n: number,
  skip: (z: LevelZone) => boolean): LevelZone[] {
  const close = zones.filter(z => z.side === side && !skip(z) && dist(z, price) <= window)
    .sort((a, b) => dist(a, price) - dist(b, price));
  if (close.length === 0) return [];
  const rest = close.slice(1).sort((a, b) => b.strength - a.strength || dist(a, price) - dist(b, price));
  return [close[0], ...rest.slice(0, n - 1)];
}

/** The 5-minute pane's lines, from its own map (`five_minute`). */
export function mapPick(zones: LevelZone[], price: number): Set<LevelZone> {
  return new Set<LevelZone>([
    ...pickSide(zones, price, 'above', LEVEL_MAP_WINDOW_PCT, LEVEL_PER_SIDE, () => false),
    ...pickSide(zones, price, 'below', LEVEL_MAP_WINDOW_PCT, LEVEL_PER_SIDE, () => false),
    ...zones.filter(z => z.side === 'at'),
    ...zones.filter(z => has(z, 'hod') || has(z, 'lod')),
  ]);
}

/** The Full Day pane's lines. */
export function dailyPick(zones: LevelZone[], price: number): Set<LevelZone> {
  return new Set<LevelZone>([
    ...pickSide(zones, price, 'above', LEVEL_DAILY_WINDOW_PCT, LEVEL_PER_SIDE, isYesterday),
    ...pickSide(zones, price, 'below', LEVEL_DAILY_WINDOW_PCT, LEVEL_PER_SIDE, isYesterday),
    ...zones.filter(z => z.side === 'at'),
    ...zones.filter(z => z.members.some(m => YESTERDAY.has(m.kind))),
  ]);
}

function dashOf(z: LevelZone): number[] {
  if (isYesterday(z)) return DASH.yesterday;
  if (isDaily(z)) return DASH.daily;
  return DASH.solid;
}

function widthOf(z: LevelZone): number {
  return z.strength >= STRONG && !roundOnly(z) ? 2 : 1;
}

export interface LevelScene {
  levels: SceneLevel[];
  ticks: SceneTick[];
  tags: SceneEdgeTag[];
  count: number;
}

const EMPTY_SCENE: LevelScene = { levels: [], ticks: [], tags: [], count: 0 };
/** Two zones this close are the same price. */
const SAME = 0.005;

/** The picked zones in bands (2026-10-13, one label per price): zones on one side of the price whose edges are within
 * `LEVEL_FOLD_PCT` of each other are one band, at most twice that wide. Lowest first. */
export function bands(picked: LevelZone[]): LevelZone[][] {
  const out: LevelZone[][] = [];
  for (const z of [...picked].sort((a, b) => a.lo - b.lo)) {
    const last = out[out.length - 1];
    const lo = last ? Math.min(...last.map(x => x.lo)) : 0;
    const hi = last ? Math.max(...last.map(x => x.hi)) : 0;
    if (last && last[0].side === z.side && near(hi, z.lo) && z.hi - lo <= 2 * LEVEL_FOLD_PCT * lo) last.push(z);
    else out.push([z]);
  }
  return out;
}

/** A band as one zone: from its lowest edge to its highest, every member, the strongest zone's side and strength. */
function bandZone(group: LevelZone[]): LevelZone {
  if (group.length === 1) return group[0];
  const strongest = group.reduce((a, b) => (b.strength > a.strength ? b : a));
  const lo = Math.min(...group.map(z => z.lo));
  const hi = Math.max(...group.map(z => z.hi));
  const side = strongest.side;
  return {
    ...strongest, lo, hi, price: side === 'above' ? lo : side === 'below' ? hi : strongest.price,
    members: group.flatMap(z => z.members),
  };
}

/** The picked zones as lines with labels and off-view tags, a band of near ones as one; the rest as ticks when
 * `ticks`. */
function sceneOf(zones: LevelZone[], pick: Set<LevelZone>, ticks: boolean): LevelScene {
  const out: LevelScene = { levels: [], ticks: [], tags: [], count: zones.length };
  if (ticks) {
    for (const z of zones) if (!pick.has(z)) out.ticks.push({ price: z.price, color: zoneColor(z), hoverId: levelHoverId(z) });
  }
  // Highest first, as the map lists them.
  for (const group of bands(zones.filter(z => pick.has(z))).reverse()) {
    const z = bandZone(group);
    const color = zoneColor(z);
    const label = group.length > 1 ? bandLabel(z) : shortLabel(z);
    const hoverId = group.length > 1 ? foldHoverId(label, group.map(levelHoverId)) : levelHoverId(z);
    out.levels.push({
      lo: z.lo, hi: z.hi, price: z.price, color, dash: dashOf(z), width: widthOf(z), label, hoverId,
      foldName: foldWord(z),
      ...(roundOnly(z) ? { lineAlpha: LEVEL_ROUND_LINE_ALPHA } : {}),
      priority: has(z, 'hod') ? EDGE_PRIORITY.highOfDay : EDGE_PRIORITY.level,
    });
    out.tags.push({ price: z.price, label: z.tag, color });
  }
  return out;
}

/** The 5-minute or Full Day pane's level lines, labels, axis ticks and off-view tags. */
export function levelScene(read: StockRead, pane: LevelPane): LevelScene {
  const lm = read.level_map;
  const price = read.price ?? lm?.price ?? null;
  if (!lm || price === null || price <= 0) return EMPTY_SCENE;
  const zones = pane === 'map' ? lm.five_minute ?? [] : lm.daily;
  return sceneOf(zones, pane === 'map' ? mapPick(zones, price) : dailyPick(zones, price), true);
}

/** The 1-minute pane's levels, from today's 1-minute map (operator report 2026-09-30: a double top two
 * 1-minute candles made belongs where those candles can be seen): the high of day, the zone the price is
 * on, the nearest zone over and under it that the candles made (a top or a bottom tested twice or more),
 * the nearest round number each side, and the plan's levels between its stop and target. No ticks: the
 * 5-minute pane lists the day. */
export function minuteScene(read: StockRead): LevelScene {
  const lm = read.level_map;
  const price = read.price ?? lm?.price ?? null;
  if (!lm || price === null || price <= 0) return EMPTY_SCENE;
  const zones = lm.intraday;
  const made = (z: LevelZone) => z.members.some(m => CANDLE.has(m.kind));
  const nearest = (keep: (z: LevelZone) => boolean, side: LevelZone['side']) => zones
    .filter(z => z.side === side && keep(z)).sort((a, b) => dist(a, price) - dist(b, price))[0];
  const between = read.plan?.levels?.between ?? [];
  const pick = new Set<LevelZone>([
    ...zones.filter(z => has(z, 'hod')),
    ...zones.filter(z => z.side === 'at' && (made(z) || isRound(z))),
    ...[nearest(made, 'above'), nearest(made, 'below'), nearest(isRound, 'above'), nearest(isRound, 'below')]
      .filter((z): z is LevelZone => z !== undefined),
    ...zones.filter(z => between.some(b => Math.abs(b.lo - z.lo) < SAME && Math.abs(b.hi - z.hi) < SAME)),
  ]);
  return sceneOf(zones, pick, false);
}

/** The note in the pane's corner. */
export function levelNote(read: StockRead, pane: LevelPane): string | null {
  const lm = read.level_map;
  if (!lm) return null;
  if (pane === 'daily' && lm.daily_error) return `Daily levels: ${lm.daily_error}`;
  if (pane === 'daily') return `Daily levels (${lm.daily.length})`;
  // A backend older than the 5-minute map sends none: say so rather than draw the 1-minute map here.
  if (lm.five_minute === null) return '5-minute levels: the backend is older than this desk -- restart it';
  return `5-minute levels (${lm.five_minute.length})`;
}
