/**
 * Pure: a leaderboard answer as the Scanner's tables, and what each list says
 * when it has no rows. A leaderboard row maps field by field onto the
 * ScannerRow the tables already render; nothing is derived except
 * `change_abs` (price - prev_close, only when both are known). Every unknown
 * stays null -- the tables render it as their dash, never 0.
 */
import { etTime } from '../sim/historicalReplayFormat';
import type { ScannerRow } from '../types/scanner';
import {
  LEADERBOARD_BOARD_MARKET,
  LEADERBOARD_CATALYSTS_NOT_RECORDED,
  LEADERBOARD_GAP_DAY_NOT_RECORDED,
  LEADERBOARD_GAP_STOP_WORD,
  LEADERBOARD_LABEL_LOADING,
  LEADERBOARD_NOT_REBUILT,
  LEADERBOARD_SOURCE_WORD,
  leaderboardErrorText,
  leaderboardGapText,
  leaderboardLabel,
  leaderboardListEmpty,
  leaderboardListNotRecorded,
  leaderboardListUnavailable,
  leaderboardLoadingText,
} from './leaderboardConstants';
import type {
  LeaderboardAt,
  LeaderboardGap,
  LeaderboardRow,
  ReplayListKey,
  ScannerReplay,
  ScannerReplayTables,
} from './leaderboardTypes';

/** "07:42" (Eastern) for an epoch second. */
export const etClock = (epochSeconds: number): string => etTime(epochSeconds).slice(0, 5);

export const EMPTY_REPLAY_TABLES: ScannerReplayTables = Object.freeze({
  gappers: [], gainers: [], losers: [], afterhours: [], largeCap: [],
}) as ScannerReplayTables;

/** One leaderboard row as a Scanner row. `has_news: null` is unknown (`news_unknown`), not "no news". */
export function scannerRowFromLeaderboard(row: LeaderboardRow): ScannerRow {
  const changeAbs = row.price != null && row.prev_close != null ? row.price - row.prev_close : null;
  return {
    symbol: row.symbol,
    exchange: row.exchange,
    ...(row.rank != null ? { rank: row.rank } : {}),
    price: row.price,
    prev_close: row.prev_close,
    change_pct: row.change_pct,
    change_abs: changeAbs,
    gap_percent: row.gap_pct,
    volume: row.volume,
    rel_volume: row.rvol,
    // The basis names what the RVOL divides by, like the live row's source mark.
    rvol_source: row.rvol != null ? row.rvol_basis : null,
    has_news: row.has_news === true,
    news_unknown: row.has_news == null,
    // The row knows when news was first seen, not the newest headline: no flame is invented.
    newest_headline_at: null,
    market_cap: row.market_cap,
    float: row.float_shares,
    short_interest: null,
    short_ratio: null,
    halted: row.halted,
  };
}

const byRank = (a: LeaderboardRow, b: LeaderboardRow) =>
  (a.rank ?? Number.MAX_SAFE_INTEGER) - (b.rank ?? Number.MAX_SAFE_INTEGER);

function rowsOf(answer: LeaderboardAt, board: string): ScannerRow[] {
  return [...(answer.boards[board]?.rows ?? [])].sort(byRank).map(scannerRowFromLeaderboard);
}

/** The five Scanner lists from one answer; a rebuilt day's `market` board is the Gainers list. */
export function replayTables(answer: LeaderboardAt): ScannerReplayTables {
  if (answer.gap || !answer.covered) return EMPTY_REPLAY_TABLES;
  if (answer.source === 'reconstructed') {
    return { ...EMPTY_REPLAY_TABLES, gainers: rowsOf(answer, LEADERBOARD_BOARD_MARKET) };
  }
  return {
    gappers: rowsOf(answer, 'gappers'),
    gainers: rowsOf(answer, 'gainers'),
    losers: rowsOf(answer, 'losers'),
    afterhours: rowsOf(answer, 'afterhours'),
    largeCap: rowsOf(answer, 'large_cap'),
  };
}

/** The playback state for one answer. */
export function replayFromAnswer(date: string, minute: number, answer: LeaderboardAt): ScannerReplay {
  const boardStates: Partial<Record<string, string | null>> = {};
  for (const [name, board] of Object.entries(answer.boards)) boardStates[name] = board.state;
  return {
    date,
    minute,
    status: 'ready',
    source: answer.source,
    minuteTs: answer.gap ? null : answer.minute_ts,
    gap: answer.gap,
    error: null,
    tables: replayTables(answer),
    boardStates,
    leaders: answer.leaders,
  };
}

export function replayPending(date: string, minute: number, error: string | null = null): ScannerReplay {
  return {
    date, minute, status: error ? 'error' : 'loading', source: null, minuteTs: null, gap: null,
    error, tables: EMPTY_REPLAY_TABLES, boardStates: {}, leaders: [],
  };
}

/** "No board: Nova not running 09:12-09:31 (Nova stopped unexpectedly)". */
export function gapText(gap: LeaderboardGap): string {
  if (gap.reason === 'outside_session') return leaderboardGapText(gap.reason, '');
  if (gap.start == null || gap.end == null) return leaderboardGapText(gap.reason, '');
  const start = etClock(gap.start);
  const end = etClock(gap.end);
  // A day with no recorder run at all reads as that, not as 04:00-20:01.
  if (gap.reason === 'not_recorded' && start <= '04:00' && end >= '20:00') return LEADERBOARD_GAP_DAY_NOT_RECORDED;
  const stop = gap.stop ? LEADERBOARD_GAP_STOP_WORD[gap.stop] : undefined;
  const text = leaderboardGapText(gap.reason, `${start}-${end}`);
  return stop ? `${text} (${stop})` : text;
}

/** The minute the label and the absences name: the board's own, else the playhead minute asked for. */
export const replayClock = (replay: ScannerReplay): string => etClock(replay.minuteTs ?? replay.minute);

/** `Sim · 2026-09-21 07:42 ET · recorded` / `rebuilt` / `loading`. */
export function replayLabel(replay: ScannerReplay): string {
  const word = replay.status === 'loading'
    ? LEADERBOARD_LABEL_LOADING
    : replay.source && !replay.gap ? LEADERBOARD_SOURCE_WORD[replay.source] ?? replay.source : '';
  return leaderboardLabel(replay.date, replayClock(replay), word);
}

/** The header's reason chip: a gap or a failure; null while a board is shown. */
export function replayNotice(replay: ScannerReplay): string | null {
  if (replay.status === 'error') return leaderboardErrorText(replayClock(replay), replay.error ?? '');
  return replay.gap ? gapText(replay.gap) : null;
}

const LIST_BOARD: Record<ReplayListKey, string> = {
  gappers: 'gappers', gainers: 'gainers', losers: 'losers', afterhours: 'afterhours', large_cap: 'large_cap',
};
const LIST_LABEL: Record<ReplayListKey, string> = {
  gappers: 'gappers', gainers: 'gainers', losers: 'losers', afterhours: 'after-hours movers', large_cap: 'large cap movers',
};

/** What an empty list says while the Scanner follows the playhead. Never "quiet market" copy. */
export function replayListAbsence(replay: ScannerReplay, list: string): string {
  const clock = replayClock(replay);
  if (replay.status === 'loading') return leaderboardLoadingText(clock);
  if (replay.status === 'error') return leaderboardErrorText(clock, replay.error ?? '');
  if (list === 'catalysts') return LEADERBOARD_CATALYSTS_NOT_RECORDED;
  if (replay.gap) return gapText(replay.gap);
  const key = (list in LIST_BOARD ? list : 'gainers') as ReplayListKey;
  const label = LIST_LABEL[key];
  if (replay.source === 'reconstructed') {
    return key === 'gainers' ? leaderboardListEmpty(label, clock) : LEADERBOARD_NOT_REBUILT;
  }
  const board = LIST_BOARD[key];
  if (!(board in replay.boardStates)) return leaderboardListNotRecorded(label, clock);
  const state = replay.boardStates[board];
  if (state === 'unavailable' || state === 'feed_down') return leaderboardListUnavailable(label, clock, state);
  return leaderboardListEmpty(label, clock);
}
