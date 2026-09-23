/** Pure: what the HOD strip says while it follows the Sim playhead (ADR 022). */
import {
  HOD_REPLAY_FEED_TITLE,
  LEADERBOARD_RECORD_SETTLE_SEC,
  hodReplayEmpty,
  hodReplayError,
  hodReplayFeedLabel,
  hodReplayLoading,
} from '../leaderboard/leaderboardConstants';
import { etClock } from '../leaderboard/leaderboardRows';
import type { HodMomoReplayState } from './useHodMomoReplay';

/** "07:42": the playhead minute the history was read for. */
export const hodReplayClock = (replay: HodMomoReplayState): string =>
  etClock(replay.minute + LEADERBOARD_RECORD_SETTLE_SEC);

/** The header's feed word in place of `feed live`. */
export function hodReplayFeed(replay: HodMomoReplayState): { text: string; title: string } {
  return { text: hodReplayFeedLabel(hodReplayClock(replay)), title: HOD_REPLAY_FEED_TITLE };
}

/** The empty strip: loading, a failed read, or no alert raised yet at the playhead. */
export function hodReplayEmptyText(replay: HodMomoReplayState): string {
  const clock = hodReplayClock(replay);
  if (replay.error) return hodReplayError(replay.error);
  if (replay.loading) return hodReplayLoading(clock);
  return hodReplayEmpty(replay.date, clock);
}
