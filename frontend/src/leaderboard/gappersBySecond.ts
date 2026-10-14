/**
 * Pure: a rebuilt day's Gappers by the second laid over the minute board (ADR 023 amendment 2026-10-13), and
 * what the Scanner header says about it. The second's rows replace the Gappers list only when they are of the
 * board's day and at most `LEADERBOARD_SECONDS_KEEP_SEC` behind the playhead -- never ahead of it, never from a
 * second the playhead jumped away from; otherwise the list is the minute board and the header says why.
 */
import {
  LEADERBOARD_BOARD_GAPPERS,
  LEADERBOARD_SECONDS_KEEP_SEC,
  LEADERBOARD_SECONDS_STOPPED,
  leaderboardSecondsBuilding,
  leaderboardSecondsError,
  leaderboardSecondsFailed,
  leaderboardSecondsShown,
  leaderboardSecondsUnavailable,
} from './leaderboardConstants';
import { etClockSeconds, scannerRowFromLeaderboard } from './leaderboardRows';
import type { LeaderboardSecondsAt, ScannerReplay, ScannerReplaySeconds } from './leaderboardTypes';

/** The last answer the desk got, with the playhead second it asked at (or the request's failure). */
export interface GappersBySecondAnswer {
  date: string;
  asked: number | null;
  answer: LeaderboardSecondsAt | null;
  error: string | null;
}

/** A day whose Gappers can be filled in by the second: a rebuilt board with a Gappers list. */
export function gappersBySecondDay(replay: ScannerReplay | null): string | null {
  if (!replay || replay.source !== 'reconstructed') return null;
  return LEADERBOARD_BOARD_GAPPERS in replay.boardStates ? replay.date : null;
}

/** Whether the answer's rows stand at playhead second `second`. */
export function bySecondStands(answer: LeaderboardSecondsAt | null, second: number | null): boolean {
  if (!answer || answer.status !== 'ready' || answer.secondTs == null || second == null) return false;
  const behind = second - answer.secondTs;
  return behind >= 0 && behind <= LEADERBOARD_SECONDS_KEEP_SEC;
}

/** The replay with its Gappers list at the second when the answer stands, and the build's state either way. */
export function withGappersBySecond(
  replay: ScannerReplay | null,
  latest: GappersBySecondAnswer | null,
  second: number | null,
): ScannerReplay | null {
  const day = gappersBySecondDay(replay);
  if (!replay || day == null || !latest || latest.date !== day) return replay;
  const answer = latest.answer;
  const shown = replay.status === 'ready' && !replay.gap && bySecondStands(answer, second);
  const bySecond: ScannerReplaySeconds = {
    status: latest.error != null ? 'error' : answer?.status ?? 'none',
    reason: answer?.reason ?? null,
    stage: answer?.stage ?? null,
    done: answer?.done ?? null,
    total: answer?.total ?? null,
    error: latest.error ?? answer?.error ?? null,
    secondTs: shown ? answer?.secondTs ?? null : null,
    shown,
  };
  if (!shown || !answer) return { ...replay, bySecond };
  const gappers = answer.rows.map(row => scannerRowFromLeaderboard(row, answer.secondTs));
  return { ...replay, tables: { ...replay.tables, gappers }, bySecond };
}

/** The Scanner header's word on it; null when there is nothing to say (no request yet, or ready between answers). */
export function bySecondNotice(bySecond: ScannerReplaySeconds | null | undefined): string | null {
  if (!bySecond) return null;
  if (bySecond.shown && bySecond.secondTs != null) return leaderboardSecondsShown(etClockSeconds(bySecond.secondTs));
  switch (bySecond.status) {
    case 'queued':
    case 'building':
      return leaderboardSecondsBuilding(bySecond.stage, bySecond.done, bySecond.total);
    case 'failed':
      return leaderboardSecondsFailed(bySecond.error);
    case 'stopped':
      return LEADERBOARD_SECONDS_STOPPED;
    case 'unavailable':
      return leaderboardSecondsUnavailable(bySecond.reason);
    case 'error':
      return leaderboardSecondsError(bySecond.error ?? '');
    default:
      return null;
  }
}
