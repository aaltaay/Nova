/**
 * The read while you hold the stock (ADR 036 amendment 2026-10-01): the wire's `held`, its types, and
 * the pure words the plan box, the ladder and the 10-second chart use. Operator ask: "If I enter a trade,
 * can it tell me on the chart when I should sell ... if we pass that level, okay, this is the next level".
 *
 * A field the wire lacks or mistypes is dropped or null -- never guessed.
 */
import { normalizeLevelNote } from './levelMapNormalize';
import { list, normalizeCheck, num, obj, str } from './normalize';
import type { PlanLevelNote } from './levelTypes';
import type { PlanCheck } from './types';

export type HeldRole = 'then' | 'next' | 'now' | 'through' | 'broke' | 'support' | 'resistance' | 'stop' | 'cost';
export type HeldStopSource = 'yours' | 'proposed' | 'nova';

export interface HeldRow {
  role: HeldRole;
  price: number;
  text: string;
  /** R of the trade at that price (the risk you measure R in); null when R is unknown. */
  r: number | null;
  /** Dollars of the trade at that price; null for a round's row. */
  usd: number | null;
}

export interface HeldStop {
  price: number;
  source: HeldStopSource;
  rule: string;
  printed: boolean;
}

export interface HeldRaise {
  to: number;
  round: number;
  /** When the candle that closed over the round closed (epoch seconds). */
  at: number;
  text: string;
}

export interface HeldLevels {
  room: PlanLevelNote | null;
  target: PlanLevelNote | null;
  stop: PlanLevelNote | null;
  next: PlanLevelNote | null;
  recent: PlanLevelNote | null;
}

export interface StockHeld {
  /** ADR 048: a short's read is the mirror -- its stop over the price, its levels under it, lower not raise.
   * Absent: long. */
  side?: 'long' | 'short';
  qty: number;
  avg: number;
  price: number | null;
  open_usd: number | null;
  r: number | null;
  risk: number | null;
  since: number | null;
  stop: HeldStop | null;
  raise: HeldRaise | null;
  /** A short's: the broke round its buy stop may come down to (`to` the stop, `round` the round). */
  lower?: HeldRaise | null;
  target: { price: number; rule: string; traded_at: number | null } | null;
  ladder: HeldRow[];
  broke: { round: number; at: number; close: number }[];
  through: { round: number; at: number | null; high: number | null }[];
  levels: HeldLevels;
  checks: PlanCheck[];
}

const ROLES: ReadonlySet<string> = new Set<HeldRole>([
  'then', 'next', 'now', 'through', 'broke', 'support', 'resistance', 'stop', 'cost',
]);
const SOURCES: ReadonlySet<string> = new Set<HeldStopSource>(['yours', 'proposed', 'nova']);

function row(raw: unknown): HeldRow | null {
  const r = obj(raw);
  const price = num(r?.price);
  if (!r || price === null || typeof r.role !== 'string' || !ROLES.has(r.role)) return null;
  return { role: r.role as HeldRole, price, text: str(r.text) ?? '', r: num(r.r), usd: num(r.usd) };
}

function stop(raw: unknown): HeldStop | null {
  const s = obj(raw);
  const price = num(s?.price);
  if (!s || price === null || typeof s.source !== 'string' || !SOURCES.has(s.source)) return null;
  return { price, source: s.source as HeldStopSource, rule: str(s.rule) ?? '', printed: s.printed === true };
}

function raiseOf(raw: unknown): HeldRaise | null {
  const r = obj(raw);
  const to = num(r?.to);
  const round = num(r?.round);
  if (!r || to === null || round === null) return null;
  return { to, round, at: num(r.at) ?? 0, text: str(r.text) ?? '' };
}

/** `held` off the wire; null when the read carries none (nothing held, or an older backend). */
export function normalizeHeld(raw: unknown): StockHeld | null {
  const h = obj(raw);
  const qty = num(h?.qty);
  const avg = num(h?.avg);
  if (!h || qty === null || avg === null || qty <= 0) return null;
  const t = obj(h.target);
  const tPrice = num(t?.price);
  const lv = obj(h.levels) ?? {};
  return {
    side: h.side === 'short' ? 'short' : 'long',
    qty,
    avg,
    price: num(h.price),
    open_usd: num(h.open_usd),
    r: num(h.r),
    risk: num(h.risk),
    since: num(h.since),
    stop: stop(h.stop),
    raise: raiseOf(h.raise),
    lower: raiseOf(h.lower),
    target: t && tPrice !== null ? { price: tPrice, rule: str(t.rule) ?? '', traded_at: num(t.traded_at) } : null,
    ladder: list(h.ladder, row),
    broke: list(h.broke, x => {
      const b = obj(x);
      const round = num(b?.round);
      return b && round !== null ? { round, at: num(b.at) ?? 0, close: num(b.close) ?? round } : null;
    }),
    through: list(h.through, x => {
      const b = obj(x);
      const round = num(b?.round);
      // A long's through row has the candle's high; a short's its low.
      return b && round !== null ? { round, at: num(b.at), high: num(b.high) ?? num(b.low) } : null;
    }),
    levels: {
      room: normalizeLevelNote(lv.room),
      target: normalizeLevelNote(lv.target),
      stop: normalizeLevelNote(lv.stop),
      next: normalizeLevelNote(lv.next),
      recent: normalizeLevelNote(lv.recent),
    },
    checks: list(h.checks, normalizeCheck),
  };
}

/** The ladder chip's word. */
export const ROLE_WORDS: Record<HeldRole, string> = {
  then: 'THEN',
  next: 'NEXT',
  now: 'NOW',
  through: 'THROUGH',
  broke: 'BROKE',
  support: 'SUPPORT',
  resistance: 'RESIST',
  stop: 'STOP',
  cost: 'COST',
};

/** The rows the 10-second chart draws as lines (the price is the chart's own). */
export const CHART_ROLES: ReadonlySet<HeldRole> = new Set<HeldRole>([
  'then', 'next', 'through', 'broke', 'support', 'resistance', 'stop', 'cost',
]);

/** "the stop Nova proposes", "your stop", "Nova's stop". */
export function stopWords(s: HeldStop | null): string {
  if (!s) return 'no stop';
  return s.source === 'nova' ? "Nova's stop" : s.source === 'yours' ? 'your stop' : 'the stop Nova proposes';
}

/** The first row of a role, or null. */
export function rowOf(held: StockHeld | null, role: HeldRole): HeldRow | null {
  return held?.ladder.find(r => r.role === role) ?? null;
}
