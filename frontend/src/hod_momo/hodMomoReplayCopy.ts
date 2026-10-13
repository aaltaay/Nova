/** Pure: what the HOD strip says while it follows the Sim playhead (ADR 023). */
import {
  HOD_REPLAY_FEED_TITLE,
  HOD_REPLAY_NO_HISTORY_COUNT,
  HOD_REPLAY_NO_HISTORY_TITLE,
  LEADERBOARD_RECORD_SETTLE_SEC,
  hodReplayEmpty,
  hodReplayError,
  hodReplayFeedLabel,
  hodReplayLoading,
  hodReplayNoHistory,
} from '../leaderboard/leaderboardConstants';
import { etClock } from '../leaderboard/leaderboardRows';
import { hodMomoStripSinceLabel } from './hodMomoStripConstants';
import type { HodMomoReplayState } from './useHodMomoReplay';

/** "07:42": the playhead minute the history was read for. */
export const hodReplayClock = (replay: HodMomoReplayState): string =>
  etClock(replay.minute + LEADERBOARD_RECORD_SETTLE_SEC);

/** The header's feed word in place of `feed live`. */
export function hodReplayFeed(replay: HodMomoReplayState): { text: string; title: string } {
  return { text: hodReplayFeedLabel(hodReplayClock(replay)), title: HOD_REPLAY_FEED_TITLE };
}

/** A day Nova kept no HOD Momo record of says so; null on a recorded day (or before the first read answers). */
export function hodReplayNoHistoryText(replay: HodMomoReplayState): string | null {
  return replay.recorded === false ? hodReplayNoHistory(replay.date) : null;
}

/** The empty strip: a failed read, a day with no history, loading, or no alert raised yet at the playhead. */
export function hodReplayEmptyText(replay: HodMomoReplayState): string {
  const clock = hodReplayClock(replay);
  if (replay.error) return hodReplayError(replay.error);
  const absent = hodReplayNoHistoryText(replay);
  if (absent) return absent;
  if (replay.loading) return hodReplayLoading(clock);
  return hodReplayEmpty(replay.date, clock);
}

/** Why the empty strip says what it says, when there is more to it than the line. */
export function hodReplayEmptyTitle(replay: HodMomoReplayState): string | undefined {
  return replay.recorded === false && !replay.error ? HOD_REPLAY_NO_HISTORY_TITLE : undefined;
}

/** The header's count: "N alerts since HH:MM", or, on a day with no history, that absence -- never "0 alerts". */
export function hodStripCountLabel(replay: HodMomoReplayState | null, count: number, since: string | null): string {
  return replay?.recorded === false ? HOD_REPLAY_NO_HISTORY_COUNT : hodMomoStripSinceLabel(count, since);
}
