/**
 * Which of the day's levels each chart draws (ADR 036 amendment 2026-09-30, operator ask: "we can
 * identify major resistance/support levels ... sometimes we have to look at the very obvious
 * resistance/support levels"). Pure. Each chart carries the levels that come from it:
 *
 * - **5-minute** (`map`): today's map. Per side, the nearest zone and the strongest others within 12% of
 *   the price (three in all); the zone the price is on; the high and low of day; the nearest whole and
 *   half dollar each side; yesterday's levels within 25%. Each gets a line and a label at the right edge.
 * - **Full Day** (`daily`): the daily map, the same way within 40%, with yesterday's levels.
 * - **1-minute**: only the trade's levels -- `chartShapes` draws the plan's `between` as price lines.
 *
 * Every other zone of a map is a short tick on the price axis. A label or a tick names its hover card
 * (`level:<zone id>`), whose story is `levelStory`. Nothing here is estimated: every price is the
 * backend's level map.
 */
import {
  LEVEL_COLORS,
  LEVEL_DAILY_WINDOW_PCT,
  LEVEL_MAP_WINDOW_PCT,
  LEVEL_PER_SIDE,
  LEVEL_YESTERDAY_WINDOW_PCT,
} from './constants';
import type { SceneLevel, SceneTick } from './levelRender';
import type { SceneEdgeTag } from './SetupShapesPrimitive';
import type { ShapeStory } from './ShapeTip';
import type { LevelMember, LevelStudy, LevelZone } from './levelTypes';
import type { StockRead } from './types';

export type LevelPane = 'map' | 'daily';

const ROUND = new Set(['whole', 'half']);
const YESTERDAY = new Set(['yday_high', 'yday_low', 'prior_close']);
const DAILY = new Set(['daily_highs', 'daily_lows', 'daily_high', 'gap', 'sma200']);
/** A zone this strong gets the heavier line. */
const STRONG = 8;
const DASH = { round: [7, 4], yesterday: [1, 3], daily: [4, 3], solid: [] as number[] };

export function levelHoverId(z: LevelZone): string {
  return `level:${z.id}`;
}

const isRound = (z: LevelZone) => z.members.some(m => ROUND.has(m.kind));
const isYesterday = (z: LevelZone) => z.members.every(m => YESTERDAY.has(m.kind));
const isDaily = (z: LevelZone) => z.members.every(m => DAILY.has(m.kind));
const has = (z: LevelZone, kind: LevelMember['kind']) => z.members.some(m => m.kind === kind);

function dist(z: LevelZone, price: number): number {
  return Math.abs(z.price - price) / price;
}

/** Per side, the nearest zone and the strongest others within `window` of the price: `n` in all. */
function pickSide(zones: LevelZone[], price: number, side: 'above' | 'below', window: number, n: number,
  skip: (z: LevelZone) => boolean): LevelZone[] {
  const near = zones.filter(z => z.side === side && !skip(z) && dist(z, price) <= window)
    .sort((a, b) => dist(a, price) - dist(b, price));
  if (near.length === 0) return [];
  const rest = near.slice(1).sort((a, b) => b.strength - a.strength || dist(a, price) - dist(b, price));
  return [near[0], ...rest.slice(0, n - 1)];
}

/** The 5-minute pane's lines. */
export function mapPick(zones: LevelZone[], price: number): Set<LevelZone> {
  const pick = new Set<LevelZone>([
    ...pickSide(zones, price, 'above', LEVEL_MAP_WINDOW_PCT, LEVEL_PER_SIDE, isYesterday),
    ...pickSide(zones, price, 'below', LEVEL_MAP_WINDOW_PCT, LEVEL_PER_SIDE, isYesterday),
    ...zones.filter(z => z.side === 'at'),
    ...zones.filter(z => has(z, 'hod') || has(z, 'lod')),
    ...zones.filter(z => isYesterday(z) && dist(z, price) <= LEVEL_YESTERDAY_WINDOW_PCT),
  ]);
  for (const side of ['above', 'below'] as const) {
    for (const kind of ['whole', 'half'] as const) {
      const r = zones.filter(z => z.side === side && has(z, kind)).sort((a, b) => dist(a, price) - dist(b, price))[0];
      if (r) pick.add(r);
    }
  }
  return pick;
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

export function zoneColor(z: LevelZone): string {
  if (isRound(z)) return LEVEL_COLORS.round;
  if (isYesterday(z)) return LEVEL_COLORS.yesterday;
  if (isDaily(z)) return LEVEL_COLORS.daily;
  if (z.members.every(m => m.kind === 'vwap')) return LEVEL_COLORS.vwap;
  return z.side === 'above' ? LEVEL_COLORS.resistance : LEVEL_COLORS.support;
}

function dashOf(z: LevelZone): number[] {
  if (isRound(z)) return DASH.round;
  if (isYesterday(z)) return DASH.yesterday;
  if (isDaily(z)) return DASH.daily;
  return DASH.solid;
}

function widthOf(z: LevelZone): number {
  if (z.strength >= STRONG) return 2;
  return has(z, 'whole') ? 1.5 : 1;
}

export interface LevelScene {
  levels: SceneLevel[];
  ticks: SceneTick[];
  tags: SceneEdgeTag[];
  count: number;
}

/** The pane's level lines, labels, axis ticks and off-view tags from the read's level map. */
export function levelScene(read: StockRead, pane: LevelPane): LevelScene {
  const empty: LevelScene = { levels: [], ticks: [], tags: [], count: 0 };
  const lm = read.level_map;
  const price = read.price ?? lm?.price ?? null;
  if (!lm || price === null || price <= 0) return empty;
  const zones = pane === 'map' ? lm.intraday : lm.daily;
  const pick = pane === 'map' ? mapPick(zones, price) : dailyPick(zones, price);
  const out: LevelScene = { levels: [], ticks: [], tags: [], count: zones.length };
  for (const z of zones) {
    const color = zoneColor(z);
    const hoverId = levelHoverId(z);
    if (!pick.has(z)) {
      out.ticks.push({ price: z.price, color, hoverId });
      continue;
    }
    out.levels.push({
      lo: z.lo, hi: z.hi, price: z.price, color, dash: dashOf(z), width: widthOf(z), label: z.label, hoverId,
    });
    out.tags.push({ price: z.price, label: z.tag, color });
  }
  return out;
}

function distanceWords(z: LevelZone, price: number | null): string | null {
  if (price === null || price <= 0) return null;
  if (z.side === 'at') return 'The price is on it.';
  const d = z.price - price;
  const cents = Math.round(Math.abs(d) * 100);
  const pct = ((Math.abs(d) / price) * 100).toFixed(1);
  return `${cents}c ${d > 0 ? 'above' : 'below'} the price (${pct}%).`;
}

function memberLine(m: LevelMember): string {
  const head = m.label.charAt(0).toUpperCase() + m.label.slice(1);
  return m.note ? `${head}: ${m.note}` : head;
}

/** What the level study measured about the kinds in the zone, once each. */
function dataLines(z: LevelZone, s: LevelStudy): string[] {
  const out: string[] = [];
  const kinds = new Set(z.members.map(m => m.kind));
  if ([...kinds].some(k => ROUND.has(k))) {
    out.push(`Before it breaks, a half or whole dollar turned price back ${s.round_turn[0]}% of the time (a random price ${s.round_turn[1]}%).`);
    out.push(z.side === 'below'
      ? `A break under it: the drop went on -1.5% before +1.5% in ${s.round_lost[0]}% of breaks (random ${s.round_lost[1]}%).`
      : `Once 1c through: +1.5% before -1.5% in ${s.round_through[0]}% of breaks (random ${s.round_through[1]}%).`);
  }
  if (kinds.has('hod') || kinds.has('pmh')) {
    out.push(`Trades that reached the high of day went on past it ${s.hod_past[0]}% of the time (random ${s.hod_past[1]}%).`);
  }
  if (kinds.has('top')) {
    out.push(`Past a top tested twice or more: ${s.top_past[0]}% (random ${s.top_past[1]}%).`);
  }
  if ([...kinds].some(k => k === 'daily_highs' || k === 'daily_high')) {
    out.push(`Old daily highs did not slow gappers: ${s.daily_past[0]}% went on past them (random ${s.daily_past[1]}%). Room never counts them.`);
  }
  if (out.length === 0) out.push('Not measured on its own yet.');
  return out;
}

/** The hover card of the zone `id` names. */
export function levelStory(id: string, read: StockRead): ShapeStory | null {
  const lm = read.level_map;
  if (!lm || !id.startsWith('level:')) return null;
  const z = [...lm.intraday, ...lm.daily].find(x => levelHoverId(x) === id);
  if (!z) return null;
  const range = z.hi - z.lo > 0.004 ? ` (${z.lo.toFixed(2)}-${z.hi.toFixed(2)})` : '';
  const where = z.home === 'daily' ? 'Full Day chart' : "Today's map";
  const lines = [
    ...[distanceWords(z, read.price ?? lm.price)].filter((x): x is string => x !== null),
    ...z.members.map(memberLine),
    ...(lm.study ? ['What the data says:', ...dataLines(z, lm.study)] : []),
  ];
  return { title: `${where} · ${z.label}${range}`, lines };
}

/** The note in the pane's corner. */
export function levelNote(read: StockRead, pane: LevelPane): string | null {
  const lm = read.level_map;
  if (!lm) return null;
  if (pane === 'daily' && lm.daily_error) return `Daily levels: ${lm.daily_error}`;
  const n = pane === 'map' ? lm.intraday.length : lm.daily.length;
  return pane === 'map' ? `Today's levels (${n})` : `Daily levels (${n})`;
}
