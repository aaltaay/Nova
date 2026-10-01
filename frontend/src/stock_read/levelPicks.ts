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
 * Every other zone of a map is a short tick on the price axis. A label or a tick names its hover card
 * (`level:<zone id>`), whose story is `levelStory`. Nothing here is estimated: every price is the
 * backend's level map.
 */
import {
  LEVEL_COLORS,
  LEVEL_DAILY_WINDOW_PCT,
  LEVEL_MAP_WINDOW_PCT,
  LEVEL_PER_SIDE,
} from './constants';
import { EDGE_PRIORITY } from '../chart';
import type { SceneLevel, SceneTick } from './levelRender';
import type { SceneEdgeTag } from './sceneTypes';
import type { ShapeStory } from './ShapeTip';
import type { LevelMember, LevelZone } from './levelTypes';
import { clockEt } from './timeWords';
import type { StockRead } from './types';

export type LevelPane = 'map' | 'daily';

const ROUND = new Set(['whole', 'half']);
/** What candles make: a top or a bottom tested twice or more. */
const CANDLE = new Set(['top', 'bottom']);
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

const EMPTY_SCENE: LevelScene = { levels: [], ticks: [], tags: [], count: 0 };
/** Two zones this close are the same price. */
const SAME = 0.005;

/** The picked zones as lines with labels and off-view tags; the rest as ticks when `ticks`. */
function sceneOf(zones: LevelZone[], pick: Set<LevelZone>, ticks: boolean): LevelScene {
  const out: LevelScene = { levels: [], ticks: [], tags: [], count: zones.length };
  for (const z of zones) {
    const color = zoneColor(z);
    const hoverId = levelHoverId(z);
    if (!pick.has(z)) {
      if (ticks) out.ticks.push({ price: z.price, color, hoverId });
      continue;
    }
    out.levels.push({
      lo: z.lo, hi: z.hi, price: z.price, color, dash: dashOf(z), width: widthOf(z), label: shortLabel(z), hoverId,
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

function priceText(z: LevelZone): string {
  const r = z.members.find(m => ROUND.has(m.kind));
  return r ? `$${r.price.toFixed(2)}` : z.price.toFixed(2);
}

/** The one word that says what a level is, strongest reason first. */
const WORD: Partial<Record<LevelMember['kind'], string>> = {
  hod: 'HOD', lod: 'LOD', pmh: 'PMH', vwap: 'VWAP', open: 'Open', yday_high: 'Yest. high', yday_low: 'Yest. low',
  prior_close: 'Yest. close', daily_high: 'Old high', daily_highs: 'Daily highs', daily_lows: 'Daily lows',
  gap: 'Gap', sma200: '200-day',
};
const WORD_ORDER: LevelMember['kind'][] = [
  'hod', 'lod', 'pmh', 'vwap', 'open', 'yday_high', 'yday_low', 'prior_close', 'daily_high', 'daily_highs',
  'daily_lows', 'gap', 'sma200',
];

/** "double top", "triple bottom", "top ×5": a count of tests, in the words the backend uses. */
function countWord(kind: 'top' | 'bottom', n: number): string {
  if (n >= 4) return `${kind} ×${n}`;
  return `${n === 3 ? 'triple' : 'double'} ${kind}`;
}

function touches(z: LevelZone, kind: 'top' | 'bottom'): number {
  return z.members.filter(m => m.kind === kind).reduce((n, m) => n + (m.touches ?? 0), 0);
}

/** What the candles made of a zone in a few words: one kind by its count ("double top"), both kinds by
 * how many times price tested it ("tested 7×"); empty when no candle made it. */
function candleWords(z: LevelZone): string {
  const tops = touches(z, 'top');
  const bottoms = touches(z, 'bottom');
  if (tops && bottoms) return `tested ${tops + bottoms}×`;
  if (tops) return countWord('top', tops);
  return bottoms ? countWord('bottom', bottoms) : '';
}

/** A level's label on the chart: its price, what it is and what the candles made of it ("$17.50 · double
 * top", "23.52 · HOD · double top", "16.38 · PMH"). The card under the pointer says the rest. */
export function shortLabel(z: LevelZone): string {
  const kind = WORD_ORDER.find(k => has(z, k));
  return [priceText(z), kind ? WORD[kind] : null, candleWords(z) || null].filter(Boolean).join(' · ');
}

function money(x: number): string {
  return `$${Math.abs(x).toFixed(2)}`;
}

function whereWords(z: LevelZone, price: number | null): string {
  if (z.side === 'at') return 'The price is on it now';
  const role = z.side === 'above' ? 'Resistance' : z.side === 'below' ? 'Support' : 'Level';
  if (price === null || price <= 0) return role;
  const d = z.price - price;
  const pct = ((Math.abs(d) / price) * 100).toFixed(1);
  return `${role} · ${money(d)} ${d > 0 ? 'above' : 'below'} the price (${pct}%)`;
}

function whenWords(times: number[]): string {
  if (times.length === 0) return '';
  const sorted = [...times].sort((a, b) => a - b);
  if (sorted.length <= 3) return ` (${sorted.map(clockEt).join(', ')})`;
  return ` (${clockEt(sorted[0])} to ${clockEt(sorted[sorted.length - 1])})`;
}

const CANDLE_NAMES: Record<LevelZone['home'], string> = {
  intraday: '1-minute candles', five_minute: '5-minute candles', daily: 'daily candles',
};

/** "Whole dollar", "Half dollar", "$10 round number": the backend names each round on the stock's scale. */
function roundName(m: LevelMember): string {
  const name = m.note ?? (m.kind === 'whole' ? 'whole dollar' : 'half dollar');
  return name.charAt(0).toUpperCase() + name.slice(1);
}

/** One reason the level holds, in plain words; `candles` names the chart its tops and bottoms are on. */
function reasonWords(m: LevelMember, candles: string): string {
  const n = m.touches ?? 0;
  const days = m.note ? ` (${m.note})` : '';
  switch (m.kind) {
    case 'hod': return 'High of the day';
    case 'lod': return 'Low of the day';
    case 'pmh': return 'Premarket high';
    case 'open': return 'The 9:30 open';
    case 'vwap': return "VWAP: the day's average price";
    case 'whole':
    case 'half': return `${roundName(m)}: a round price traders watch`;
    case 'top': return `Price turned down here ${n} times on ${candles}${whenWords(m.times)}`;
    case 'bottom': return `Price bounced up from here ${n} times on ${candles}${whenWords(m.times)}`;
    case 'yday_high': return "Yesterday's high";
    case 'yday_low': return "Yesterday's low";
    case 'prior_close': return "Yesterday's close";
    case 'daily_highs': return `A daily high on ${n} days${days}`;
    case 'daily_lows': return `A daily low on ${n} days${days}`;
    case 'daily_high': return `An old daily high${days}`;
    case 'gap': return `An unfilled gap${days}`;
    case 'sma200': return 'The 200-day average';
    default: return m.label;
  }
}

/** What price usually does here, from Nova's level study, in a sentence or two. The study looked at half
 * and whole dollars on $1-$20 stocks: a round anywhere else says so instead of borrowing its figures. */
function whatHappens(z: LevelZone, roundsMeasured: boolean): string[] {
  const kinds = new Set(z.members.map(m => m.kind));
  const out: string[] = [];
  if ([...kinds].some(k => ROUND.has(k))) {
    if (!roundsMeasured) {
      out.push("Nova's study measured half and whole dollars on $1-$20 stocks only: how this stock's round numbers hold is not measured.");
    } else {
      out.push(z.side === 'below'
        ? 'Round prices often hold the first time. If this one breaks, the drop tends to keep going.'
        : 'Round prices often stall a move the first time. Once price trades through, it tends to keep running.');
    }
  }
  if (kinds.has('hod') || kinds.has('pmh')) out.push('A break above makes a new high. It slows price only a little.');
  if (kinds.has('top') && out.length === 0) out.push('Price turned back here before. It slows price a little, and usually breaks on a later try.');
  if (kinds.has('bottom') && out.length === 0) out.push('Buyers stepped in here before.');
  if (kinds.has('vwap')) out.push('Above VWAP buyers are in control; below it sellers are.');
  if ([...kinds].some(k => k === 'daily_highs' || k === 'daily_high') && out.length === 0) {
    out.push("Old daily highs did not slow gappers in Nova's study.");
  }
  return out.slice(0, 2);
}

/** The hover card of the zone `id` names: what it is, how far it is, why it is there, what usually happens. */
export function levelStory(id: string, read: StockRead): ShapeStory | null {
  const lm = read.level_map;
  if (!lm || !id.startsWith('level:')) return null;
  const z = [...lm.intraday, ...(lm.five_minute ?? []), ...lm.daily].find(x => levelHoverId(x) === id);
  if (!z) return null;
  const range = z.hi - z.lo > 0.004 ? `  ${z.lo.toFixed(2)}–${z.hi.toFixed(2)}` : '';
  const sections = [{ head: 'Why it is here', items: z.members.map(m => reasonWords(m, CANDLE_NAMES[z.home])) }];
  // A backend older than the round scale counted half dollars on every price: read as the study's.
  const next = whatHappens(z, lm.rounds?.measured ?? true);
  if (next.length) sections.push({ head: 'What usually happens', items: next });
  return {
    title: `${priceText(z)}${range}`,
    subtitle: whereWords(z, read.price ?? lm.price),
    color: zoneColor(z),
    lines: [],
    sections,
  };
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
