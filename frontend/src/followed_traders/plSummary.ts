/**
 * What a followed trader made over the span picked, in percent per share (operator ask 2026-10-14: "we can see the PL
 * per share in terms of percentage"). The feed shows no size, so their dollars cannot be known. The figure adds up the
 * P/L per share in % of each scored trade -- what the same money in every trade would have made -- and its curve is
 * that sum trade by trade, oldest exit first. Only a trade scored won, lost or scratched counts: an unscored one (an
 * exit seen only in a window, not read yet, a close the feed never saw) has no one price, so it is left out, never
 * guessed, and an open position has no exit yet. Pure. Schema: architecture/schema/followed-traders.md.
 */
import { FT_PL_OLD_BACKEND, FT_PL_WAITING } from './constants';
import { isRangePl } from './format';
import type { FollowedRecords, FollowedTrade, FollowedTrader, ScoredPoint } from './types';

export interface PlSummary {
  /** Scored trades counted. */
  count: number;
  /** Their P/L per share in % added up, percent points; 0 with none (shown as a dash, never as 0). */
  sumPct: number;
  /** `sumPct` over `count`; null with none. */
  avgPct: number | null;
  /** The sum after each trade, oldest exit first, from 0 before the first: `count + 1` values. */
  curve: number[];
}

const SCORED = new Set(['win', 'loss', 'scratch']);

/** The day's scored trades as the record route sends them (`scored`): exit time and P/L %, oldest exit first. */
export function scoredPoints(trades: readonly FollowedTrade[]): ScoredPoint[] {
  const out: ScoredPoint[] = [];
  for (const t of trades) {
    const ts = t.exit?.to_ts ?? null;
    if (!t.result || !SCORED.has(t.result) || !t.pl || isRangePl(t.pl) || ts === null) continue;
    out.push({ ts, pct: t.pl.pct });
  }
  return byExit(out);
}

/** Everyone's scored trades: each trader's, one list, oldest exit first. */
export function mergePoints(groups: readonly (readonly ScoredPoint[])[]): ScoredPoint[] {
  return byExit(groups.flat());
}

function byExit(points: ScoredPoint[]): ScoredPoint[] {
  return [...points].sort((a, b) => a.ts - b.ts);
}

/** Each % on the wire has two decimals, so their sum does too: rounded back to it, no float dust. */
function cents(x: number): number {
  return Math.round(x * 100) / 100;
}

export function summarize(points: readonly ScoredPoint[]): PlSummary {
  const curve = [0];
  let sum = 0;
  for (const p of points) {
    sum = cents(sum + p.pct);
    curve.push(sum);
  }
  const count = points.length;
  return { count, sumPct: sum, avgPct: count ? sum / count : null, curve };
}

/** Each trader's figure and everyone's over a span; `why` says why there is none (`everyone` null). */
export interface SpanPl {
  of: (name: string) => PlSummary | null;
  everyone: PlSummary | null;
  why: string | null;
}

function span(groups: Map<string, ScoredPoint[]>): SpanPl {
  return {
    of: (name) => summarize(groups.get(name) ?? []),
    everyone: summarize(mergePoints([...groups.values()])),
    why: null,
  };
}

/** The day's, from its own trades (`/day`). */
export function dayPl(traders: readonly FollowedTrader[]): SpanPl {
  return span(new Map(traders.map((t) => [t.name, scoredPoints(t.closed)])));
}

/** A Week or All span's, from `/record`; none while it is read, or from a backend that sends no `scored`. */
export function recordPl(records: FollowedRecords | null, error: string | null): SpanPl {
  if (!records) return { of: () => null, everyone: null, why: error ?? FT_PL_WAITING };
  if (records.traders.some((t) => !Array.isArray(t.scored))) return { of: () => null, everyone: null, why: FT_PL_OLD_BACKEND };
  return span(new Map(records.traders.map((t) => [t.name, t.scored ?? []])));
}
