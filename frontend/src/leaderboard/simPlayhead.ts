/**
 * The Sim playhead as the Scanner and the HOD strip need it: its day, its
 * epoch second, and the board minute it falls in -- only while the desk is
 * replaying (Sim venue, clock answered, off the live edge; `isReplayDesk`).
 *
 * The clock polls every second; the minute hook re-renders only when the
 * board minute (or the day) changes, so the leaderboard is read once a
 * minute, never every second.
 */
import { useCallback, useMemo, useSyncExternalStore } from 'react';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import { simClockResource } from '../sim/simClockResource';
import type { SimClockState } from '../sim/simClockTypes';
import { isReplayDesk } from '../sim/useSimReplayDesk';
import { LEADERBOARD_RECORD_SETTLE_SEC } from './leaderboardConstants';

/** The playhead's epoch second, or null when the clock does not state a parseable time. */
export function playheadSecond(clock: SimClockState | null | undefined): number | null {
  const ms = clock?.sim_time_et ? Date.parse(clock.sim_time_et) : NaN;
  return Number.isFinite(ms) ? Math.floor(ms / 1000) : null;
}

/** The board minute a playhead second reads: a recorded minute m is visible from m + settle. */
export function boardMinuteOf(at: number): number {
  return Math.floor((at - LEADERBOARD_RECORD_SETTLE_SEC) / 60) * 60;
}

/** The last whole second that still reads board minute `minute`. */
export function boardMinuteEnd(minute: number): number {
  return minute + 60 + LEADERBOARD_RECORD_SETTLE_SEC - 1;
}

export interface SimPlayheadMinute {
  date: string;
  minute: number;
}

/** `date|minute` while replaying, '' otherwise -- a primitive, so equal minutes never re-render. */
export function playheadMinuteKey(sim: boolean, clock: SimClockState | null | undefined): string {
  if (!isReplayDesk(sim, clock)) return '';
  const at = playheadSecond(clock);
  const date = clock?.session_date;
  if (at == null || !date) return '';
  return `${date}|${boardMinuteOf(at)}`;
}

export function parseMinuteKey(key: string): SimPlayheadMinute | null {
  if (!key) return null;
  const [date, minute] = key.split('|');
  const value = Number(minute);
  return date && Number.isFinite(value) ? { date, minute: value } : null;
}

/** The playhead second to ask a board minute with: the live playhead when it is still in that minute. */
export function playheadSecondIn(minute: number, clock: SimClockState | null | undefined): number {
  const at = playheadSecond(clock);
  const first = minute + LEADERBOARD_RECORD_SETTLE_SEC;
  if (at == null || at < first || at > boardMinuteEnd(minute)) return first;
  return at;
}

const noSubscription = () => () => {};

/** The Sim venue flag every playhead hook gates on (Live / Paper never subscribe to the clock). */
export function useSimVenue(): boolean {
  return useIbkrStatus().mode === 'sim';
}

/** The board minute at the playhead while replaying; null on Live, Paper and at the live edge. */
export function useSimPlayheadMinute(): SimPlayheadMinute | null {
  const sim = useSimVenue();
  const subscribe = useCallback(
    (listener: () => void) => (sim ? simClockResource.subscribe(listener) : noSubscription()),
    [sim],
  );
  const key = useSyncExternalStore(subscribe, () => playheadMinuteKey(sim, simClockResource.getSnapshot().data));
  return useMemo(() => parseMinuteKey(key), [key]);
}
