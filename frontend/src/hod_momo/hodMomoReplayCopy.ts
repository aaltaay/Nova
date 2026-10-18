/** Pure: what the HOD strip says while it follows the Sim playhead (ADR 023). */
import {
  HOD_REPLAY_FEED_TITLE,
  HOD_REPLAY_NO_HISTORY_COUNT,
  HOD_REPLAY_NO_HISTORY_TITLE,
  HOD_REPLAY_REBUILDING_COUNT,
  HOD_REPLAY_REBUILT_FEED_TITLE,
  LEADERBOARD_RECORD_SETTLE_SEC,
  hodReplayEmpty,
  hodReplayError,
  hodReplayFeedLabel,
  hodReplayLoading,
  hodReplayRebuildFailed,
  hodReplayRebuildUnavailable,
  hodReplayRebuilding,
  hodReplayRebuiltFeedLabel,
} from '../leaderboard';
import { etClock } from '../leaderboard';
import { hodMomoStripSinceLabel } from './hodMomoStripConstants';
import { rebuildRunning, rebuildWanted, type HodMomoReplayState } from './useHodMomoReplay';

/** "07:42": the playhead minute the history was read for. */
export const hodReplayClock = (replay: HodMomoReplayState): string =>
  etClock(replay.minute + LEADERBOARD_RECORD_SETTLE_SEC);

/** The header's feed word in place of `feed live`: `rebuilt` when the alerts are the day's rebuild. */
export function hodReplayFeed(replay: HodMomoReplayState): { text: string; title: string } {
  const clock = hodReplayClock(replay);
  return replay.source === 'rebuilt'
    ? { text: hodReplayRebuiltFeedLabel(clock), title: HOD_REPLAY_REBUILT_FEED_TITLE }
    : { text: hodReplayFeedLabel(clock), title: HOD_REPLAY_FEED_TITLE };
}

/** A day with no record and no rebuild to show yet. */
const withoutAlerts = (replay: HodMomoReplayState): boolean => replay.recorded === false && replay.source !== 'rebuilt';

/**
 * A day Nova kept no HOD Momo record of, while it has no rebuilt alerts to show: the rebuild's progress, its failure,
 * or why there is none. Null on a recorded or rebuilt day (or before the first read answers).
 */
export function hodReplayNoHistoryText(replay: HodMomoReplayState): string | null {
  if (!withoutAlerts(replay)) return null;
  const { rebuild } = replay;
  if (rebuild && (rebuildRunning(rebuild) || rebuildWanted(rebuild))) {
    return hodReplayRebuilding(replay.date, rebuild.stage, rebuild.done, rebuild.total);
  }
  if (rebuild?.status === 'failed') return hodReplayRebuildFailed(rebuild.error);
  return hodReplayRebuildUnavailable(replay.date, rebuild?.reason ?? null);
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
  if (replay.error) return undefined;
  if (replay.source === 'rebuilt') return HOD_REPLAY_REBUILT_FEED_TITLE;
  return withoutAlerts(replay) ? HOD_REPLAY_NO_HISTORY_TITLE : undefined;
}

/** The header's count: "N alerts since HH:MM", or, on a day with no alerts to show yet, why -- never "0 alerts". */
export function hodStripCountLabel(replay: HodMomoReplayState | null, count: number, since: string | null): string {
  if (!replay || !withoutAlerts(replay)) return hodMomoStripSinceLabel(count, since);
  return rebuildRunning(replay.rebuild) || rebuildWanted(replay.rebuild)
    ? HOD_REPLAY_REBUILDING_COUNT
    : HOD_REPLAY_NO_HISTORY_COUNT;
}
