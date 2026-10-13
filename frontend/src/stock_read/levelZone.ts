/**
 * One zone of the day's level map described (ADR 036 amendment 2026-09-30): its colour, its label at the right edge and
 * its card under the pointer. Pure. A zone is coloured by its strongest reason, a round number the weakest (operator
 * report 2026-10-12): coral over the price and teal under it, so a top the price climbs over turns support on the next
 * read whether or not it sits on a round; one the price is on is coral while highs made it, so touching a top is not
 * breaking it. A round number alone is a faint solid hairline (`LEVEL_ROUND_LINE_ALPHA`). Its label is its price, what
 * it is and what the candles made of it; a band of near zones says its range (`bandLabel`, 2026-10-13), and a zone
 * folded into a stronger line says one word there (`foldWord`). Its card says what it is, how far it is, why it is
 * there and what usually happens, from the level study. Which zones a chart draws is `levelPicks.ts`.
 */
import { LEVEL_COLORS } from './constants';
import type { ShapeStory } from './ShapeTip';
import type { LevelMember, LevelZone } from './levelTypes';
import { clockEt } from './timeWords';
import type { StockRead } from './types';

const ROUND = new Set(['whole', 'half']);
export const YESTERDAY = new Set(['yday_high', 'yday_low', 'prior_close']);
const DAILY = new Set(['daily_highs', 'daily_lows', 'daily_high', 'gap', 'sma200']);
const VWAP = new Set(['vwap']);
/** What the candles' highs and lows made: which side a zone the price is on holds. */
const HIGHS = new Set(['top', 'hod', 'pmh', 'yday_high', 'daily_high', 'daily_highs']);
const LOWS = new Set(['bottom', 'lod', 'yday_low', 'daily_lows']);

export function levelHoverId(z: LevelZone): string {
  return `level:${z.id}`;
}

export const isRound = (z: LevelZone) => z.members.some(m => ROUND.has(m.kind));
/** Its reasons other than a round number: what colours and dashes a zone a round sits in. */
const reasons = (z: LevelZone) => z.members.filter(m => !ROUND.has(m.kind));
/** A round number and nothing else at its price. */
export const roundOnly = (z: LevelZone) => reasons(z).length === 0;
const only = (z: LevelZone, kinds: Set<string>) => {
  const r = reasons(z);
  return r.length > 0 && r.every(m => kinds.has(m.kind));
};
export const isYesterday = (z: LevelZone) => only(z, YESTERDAY);
export const isDaily = (z: LevelZone) => only(z, DAILY);
export const has = (z: LevelZone, kind: LevelMember['kind']) => z.members.some(m => m.kind === kind);

/** A zone the price is on has not been passed: it is resistance when highs made it more than lows (a top it
 * is touching from under is not yet broken), else support. Each member counts its touches. */
function atResistance(z: LevelZone): boolean {
  let highs = 0;
  let lows = 0;
  for (const m of reasons(z)) {
    if (HIGHS.has(m.kind)) highs += m.touches ?? 1;
    else if (LOWS.has(m.kind)) lows += m.touches ?? 1;
  }
  return highs > lows;
}

export function zoneColor(z: LevelZone): string {
  if (roundOnly(z)) return LEVEL_COLORS.round;
  if (isYesterday(z)) return LEVEL_COLORS.yesterday;
  if (isDaily(z)) return LEVEL_COLORS.daily;
  if (only(z, VWAP)) return LEVEL_COLORS.vwap;
  const resistance = z.side === 'above' || (z.side === 'at' && atResistance(z));
  return resistance ? LEVEL_COLORS.resistance : LEVEL_COLORS.support;
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

/** A band's label: its range, what it is, what the candles made of it all and its round number ("4.09–4.12 · top ×8",
 * "4.48–4.50 · double bottom · $4.50"). */
export function bandLabel(z: LevelZone): string {
  const kind = WORD_ORDER.find(k => has(z, k));
  const round = z.members.find(m => ROUND.has(m.kind));
  return [`${z.lo.toFixed(2)}–${z.hi.toFixed(2)}`, kind ? WORD[kind] : null, candleWords(z) || null,
    round ? `$${round.price.toFixed(2)}` : null].filter(Boolean).join(' · ');
}

/** What a level says in a stronger line's label at its price: its round number, else what it is, else what the
 * candles made of it ("$4.00", "PMH", "top ×5"). */
export function foldWord(z: LevelZone): string {
  const round = z.members.find(m => ROUND.has(m.kind));
  if (round) return `$${round.price.toFixed(2)}`;
  const kind = WORD_ORDER.find(k => has(z, k));
  return (kind ? WORD[kind] : null) ?? (candleWords(z) || z.tag);
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
