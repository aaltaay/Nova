/**
 * What the desk window sends the Top 9 pop-up: the first nine rows of each list, in the order the
 * scanner serves them, and where the board comes from. Pure.
 *
 * The desk window is the one owner of the scanner feed; the pop-up opens no scanner socket of its
 * own and never ranks anything itself. A rank is the row's place as served (stock_view/quoteRank),
 * the same number the Trader's rank chip shows.
 */
import { rankUnknownWhy, scannerListRows } from '../stock_view';
import { replayLabel, replayNotice, type ScannerReplay } from '../leaderboard';
import type { ScannerRow } from '../types/scanner';
import { TOP_NINE_LISTS, TOP_NINE_SIZE, isTopNineList, type TopNineList } from './topNineConstants';

export const TOP_NINE_SCHEMA_VERSION = 1;

export interface TopNineRow {
  symbol: string;
  rank: number;
  /** The list's Change column, as the Scanner holds it: a fraction of the previous close (0.7 is +70%). */
  changePct: number | null;
  price: number | null;
  volume: number | null;
  float: number | null;
  halted: boolean;
}

export interface TopNineBoard {
  rows: TopNineRow[];
  /** Rows on the whole list (the rail's count). */
  total: number;
}

/** Live: today's board. Replay: the Sim playhead's board, labelled as the Scanner labels it. */
export type TopNineSource =
  | { kind: 'live' }
  | { kind: 'replay'; label: string }
  | { kind: 'unknown'; why: string };

export interface TopNineSnapshot {
  schema_version: typeof TOP_NINE_SCHEMA_VERSION;
  source: TopNineSource;
  /** The board's minute (epoch seconds): the Sim playhead's board minute, or now's minute live. Every tile's
   * chart ends here, so a halted or quiet stock's chart lines up with the others instead of ending at its last trade. */
  asOf: number;
  lists: Record<TopNineList, TopNineBoard>;
}

type FeedLike = {
  gappers: readonly ScannerRow[];
  gainers: readonly ScannerRow[];
  losers: readonly ScannerRow[];
  afterhours: readonly ScannerRow[];
  largeCap: readonly ScannerRow[];
  historyDate: string | null;
  replay?: ScannerReplay | null;
};

const EMPTY_BOARD: TopNineBoard = { rows: [], total: 0 };

function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

function toRow(row: ScannerRow, index: number): TopNineRow {
  return {
    symbol: row.symbol.trim().toUpperCase(),
    rank: index + 1,
    changePct: num(row.change_pct),
    price: num(row.price),
    volume: num(row.volume),
    float: num(row.float),
    halted: row.halted === true,
  };
}

function emptyLists(): Record<TopNineList, TopNineBoard> {
  return { gappers: EMPTY_BOARD, gainers: EMPTY_BOARD, afterhours: EMPTY_BOARD };
}

function minuteOf(epochSeconds: number): number {
  return Math.floor(epochSeconds / 60) * 60;
}

export function buildTopNineSnapshot(feed: FeedLike | null | undefined, nowMs = Date.now()): TopNineSnapshot {
  const why = rankUnknownWhy(feed);
  const replay = feed?.replay ?? null;
  const asOf = minuteOf(replay ? replay.minuteTs ?? replay.minute : nowMs / 1000);
  if (why || !feed) {
    const notice = replay ? replayNotice(replay) : null;
    return {
      schema_version: TOP_NINE_SCHEMA_VERSION,
      source: { kind: 'unknown', why: notice ?? why ?? 'No scanner feed in this window.' },
      asOf,
      lists: emptyLists(),
    };
  }
  const lists = emptyLists();
  for (const { list } of TOP_NINE_LISTS) {
    const rows = scannerListRows<ScannerRow>(feed, list).filter((r) => typeof r.symbol === 'string' && r.symbol);
    lists[list] = { rows: rows.slice(0, TOP_NINE_SIZE).map(toRow), total: rows.length };
  }
  return {
    schema_version: TOP_NINE_SCHEMA_VERSION,
    source: replay ? { kind: 'replay', label: replayLabel(replay) } : { kind: 'live' },
    asOf,
    lists,
  };
}

/** Same boards, same source: nothing new to send. */
export function sameTopNine(a: TopNineSnapshot | null, b: TopNineSnapshot | null): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

function parseRow(raw: unknown): TopNineRow | null {
  if (!raw || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  if (typeof r.symbol !== 'string' || !r.symbol) return null;
  if (typeof r.rank !== 'number' || !Number.isInteger(r.rank) || r.rank < 1) return null;
  return {
    symbol: r.symbol.toUpperCase(),
    rank: r.rank,
    changePct: num(r.changePct),
    price: num(r.price),
    volume: num(r.volume),
    float: num(r.float),
    halted: r.halted === true,
  };
}

function parseSource(raw: unknown): TopNineSource | null {
  if (!raw || typeof raw !== 'object') return null;
  const s = raw as Record<string, unknown>;
  if (s.kind === 'live') return { kind: 'live' };
  if (s.kind === 'replay' && typeof s.label === 'string') return { kind: 'replay', label: s.label };
  if (s.kind === 'unknown' && typeof s.why === 'string') return { kind: 'unknown', why: s.why };
  return null;
}

/** The pop-up's reader: an unknown schema version or a broken shape is refused, never half-read. */
export function parseTopNineSnapshot(raw: unknown): TopNineSnapshot | null {
  if (!raw || typeof raw !== 'object') return null;
  const s = raw as Record<string, unknown>;
  if (s.schema_version !== TOP_NINE_SCHEMA_VERSION) return null;
  const source = parseSource(s.source);
  if (!source || !s.lists || typeof s.lists !== 'object') return null;
  if (typeof s.asOf !== 'number' || !Number.isFinite(s.asOf)) return null;
  const lists = emptyLists();
  for (const [key, value] of Object.entries(s.lists as Record<string, unknown>)) {
    if (!isTopNineList(key) || !value || typeof value !== 'object') continue;
    const board = value as Record<string, unknown>;
    const rows = Array.isArray(board.rows) ? board.rows.map(parseRow) : [];
    if (rows.some((r) => r == null)) return null;
    lists[key] = { rows: rows as TopNineRow[], total: typeof board.total === 'number' ? board.total : rows.length };
  }
  return { schema_version: TOP_NINE_SCHEMA_VERSION, source, asOf: s.asOf, lists };
}
