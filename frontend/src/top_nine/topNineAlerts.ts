/**
 * Which boards make a sound, and the stocks muted for the day (operator ask, 2026-10-27: "we can
 * right-click and mute, because some of them are just bullshit"). Pure, except the two pref calls.
 *
 * A switch is worth a chime when a stock that is not muted moved up or came into the top nine: a stock
 * moving down is always the other side of someone's rise, so a muted stock's rise stays quiet. A halt is
 * worth the beeps when a stock that is not muted shows halted and did not on the last board of that list.
 */
import { deskTradingDay } from '../utils/deskTradingDay';
import { readPref, writePref } from '../utils/prefStore';
import { TOP_NINE_MUTED_KEY } from './topNineConstants';
import type { TopNineSwitch } from './topNineMarks';
import type { TopNineRow } from './topNineSnapshot';

export function chimeWorthy(switched: TopNineSwitch, muted: ReadonlySet<string>): boolean {
  return switched.moves.some((m) => m.kind !== 'down' && !muted.has(m.symbol));
}

export function haltedSymbols(rows: readonly TopNineRow[]): Set<string> {
  return new Set(rows.filter((r) => r.halted === true).map((r) => r.symbol));
}

/** Stocks halted now that were not on the last board; none before there is a last board. */
export function newlyHalted(
  prev: ReadonlySet<string> | null,
  rows: readonly TopNineRow[],
  muted: ReadonlySet<string>,
): string[] {
  if (!prev) return [];
  return [...haltedSymbols(rows)].filter((s) => !prev.has(s) && !muted.has(s));
}

interface MutedPref {
  day: string;
  symbols: string[];
}

function parseMuted(raw: unknown): MutedPref | null {
  if (!raw || typeof raw !== 'object') return null;
  const { day, symbols } = raw as Partial<MutedPref>;
  if (typeof day !== 'string' || !Array.isArray(symbols)) return null;
  return { day, symbols: symbols.filter((s): s is string => typeof s === 'string') };
}

/** Today's muted stocks: a mute lasts the desk's trading day (04:00 ET), so tomorrow's runner is heard. */
export function readTopNineMuted(now: number = Date.now()): Set<string> {
  const pref = readPref<MutedPref | null>(TOP_NINE_MUTED_KEY, null, parseMuted);
  return new Set(pref && pref.day === deskTradingDay(now) ? pref.symbols : []);
}

export function writeTopNineMuted(symbols: ReadonlySet<string>, now: number = Date.now()): void {
  writePref(TOP_NINE_MUTED_KEY, { day: deskTradingDay(now), symbols: [...symbols].sort() });
}
