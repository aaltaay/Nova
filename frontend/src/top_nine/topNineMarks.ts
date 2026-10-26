/**
 * Rank switches on one list, from one board to the next (operator ask, 2026-10-26: "When it shifts
 * around, like from 4th to 3rd, I want to see an obvious sign it has switched"). Pure.
 *
 * A stock is marked when its rank in the top nine differs from the last board: up, down, or new to
 * the top nine. The first board a list shows marks nothing -- there is nothing to compare it with.
 */
import {
  TOP_NINE_LOG_MAX,
  TOP_NINE_MARK_FULL_MS,
  TOP_NINE_MARK_SOFT_MS,
} from './topNineConstants';
import type { TopNineRow } from './topNineSnapshot';

export type TopNineMoveKind = 'up' | 'down' | 'new';

export interface TopNineMove {
  symbol: string;
  /** Rank on the last board, or null when it was not in the top nine. */
  from: number | null;
  to: number;
  kind: TopNineMoveKind;
  at: number;
}

/** One board's switches, for the bottom line. */
export interface TopNineSwitch {
  /** When the pop-up saw it (ms epoch). */
  at: number;
  /** The board's minute (epoch seconds) and whether it was a Sim replay's: the line shows the board's own time
   * for a replay, where the wall clock says nothing about the playhead. */
  board?: { asOf: number; replay: boolean };
  moves: TopNineMove[];
  /** Symbols that dropped out of the top nine. */
  left: string[];
}

export interface TopNineListMarks {
  /** The last board's ranks, or null before the first board. */
  ranks: Record<string, number> | null;
  /** The newest switch of each symbol still marked. */
  marks: Record<string, TopNineMove>;
  log: TopNineSwitch[];
}

export const EMPTY_LIST_MARKS: TopNineListMarks = { ranks: null, marks: {}, log: [] };

export type TopNineMarkPhase = 'full' | 'soft' | 'none';

export function diffTopNine(
  prev: Record<string, number> | null,
  rows: readonly TopNineRow[],
  at: number,
): TopNineSwitch | null {
  if (!prev) return null;
  const moves: TopNineMove[] = [];
  for (const row of rows) {
    const from = prev[row.symbol] ?? null;
    if (from === row.rank) continue;
    const kind: TopNineMoveKind = from == null ? 'new' : from > row.rank ? 'up' : 'down';
    moves.push({ symbol: row.symbol, from, to: row.rank, kind, at });
  }
  const now = new Set(rows.map((r) => r.symbol));
  const left = Object.keys(prev)
    .filter((s) => !now.has(s))
    .sort((a, b) => prev[a] - prev[b]);
  return moves.length || left.length ? { at, moves, left } : null;
}

export function markPhase(move: TopNineMove | undefined, now: number): TopNineMarkPhase {
  if (!move) return 'none';
  const age = now - move.at;
  if (age < TOP_NINE_MARK_FULL_MS) return 'full';
  if (age < TOP_NINE_MARK_SOFT_MS) return 'soft';
  return 'none';
}

/** The share of the full mark still left (1 at the switch, 0 when it fades to soft). */
export function markLeft(move: TopNineMove, now: number): number {
  return Math.max(0, Math.min(1, 1 - (now - move.at) / TOP_NINE_MARK_FULL_MS));
}

/** Take the next board of one list: new ranks, new marks, the switch logged; expired marks dropped. */
export function nextListMarks(
  state: TopNineListMarks,
  rows: readonly TopNineRow[],
  at: number,
  board?: TopNineSwitch['board'],
): { state: TopNineListMarks; switched: TopNineSwitch | null } {
  const diff = diffTopNine(state.ranks, rows, at);
  const switched = diff && board ? { ...diff, board } : diff;
  const ranks = Object.fromEntries(rows.map((r) => [r.symbol, r.rank]));
  const marks: Record<string, TopNineMove> = {};
  for (const [symbol, move] of Object.entries(state.marks)) {
    if (markPhase(move, at) !== 'none' && symbol in ranks) marks[symbol] = move;
  }
  for (const move of switched?.moves ?? []) marks[move.symbol] = move;
  const log = switched ? [switched, ...state.log].slice(0, TOP_NINE_LOG_MAX) : state.log;
  if (!switched && sameRanks(state.ranks, ranks) && Object.keys(marks).length === Object.keys(state.marks).length) {
    return { state, switched: null };
  }
  return { state: { ranks, marks, log }, switched };
}

function sameRanks(a: Record<string, number> | null, b: Record<string, number>): boolean {
  if (!a) return false;
  const ak = Object.keys(a);
  return ak.length === Object.keys(b).length && ak.every((k) => a[k] === b[k]);
}

/** `▲ 4 → 3`, `▼ 2 → 5`, `NEW`. */
export function moveText(move: TopNineMove): string {
  if (move.kind === 'new' || move.from == null) return 'NEW';
  return `${move.from} → ${move.to}`;
}
