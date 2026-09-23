/**
 * The HOD Momo strip at the Sim playhead (ADR 022, "one desk, one clock").
 *
 * Null on Live, Paper and at the live edge -- the strip stays on the live
 * socket. Off the edge it reads the day's alert history once per board minute
 * (`?until=` the minute's last second, so the server never sends a later
 * alert) and shows only the alerts raised at or before the playhead second:
 * an alert raised at 07:42:30 appears when the playhead reaches 07:42:30,
 * never at 07:42:00. The per-second filter re-renders only when the count of
 * visible alerts changes.
 */
import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from 'react';
import { HOD_HISTORY_REQUEST_FAILED, LEADERBOARD_PLAYBACK_RETRY_MS, hodMomoHistoryPath } from '../leaderboard/leaderboardConstants';
import { boardMinuteEnd, playheadSecond, useSimPlayheadMinute, useSimVenue } from '../leaderboard/simPlayhead';
import { replayRequest } from '../sim/replayRequest';
import { simClockResource } from '../sim/simClockResource';
import { uniqueAlerts } from './hodMomoWire';
import type { AlertObject } from './types';

export interface HodMomoReplayState {
  date: string;
  /** The board minute the history was read for (epoch seconds). */
  minute: number;
  loading: boolean;
  error: string | null;
}

export interface HodMomoReplay {
  state: HodMomoReplayState;
  /** Raised at or before the playhead, newest first. */
  alerts: AlertObject[];
}

/** When Nova raised the alert (`created_ts`), else its trigger `timestamp`; null when neither reads. */
export function alertRaisedAt(alert: AlertObject): number | null {
  const created = alert.created_ts;
  if (typeof created === 'number' && Number.isFinite(created) && created > 0) return created;
  const ms = typeof alert.timestamp === 'string' ? Date.parse(alert.timestamp) : NaN;
  return Number.isFinite(ms) ? ms / 1000 : null;
}

/** The history body: a list (today's route), or `{alerts: [...]}`. Undated alerts are left out. */
export function parseHodHistory(raw: unknown): AlertObject[] {
  const list = Array.isArray(raw)
    ? raw
    : raw && typeof raw === 'object' && Array.isArray((raw as { alerts?: unknown }).alerts)
      ? (raw as { alerts: unknown[] }).alerts
      : null;
  if (!list) throw new Error('Nova returned an unreadable HOD alert history.');
  const alerts = list.filter((a): a is AlertObject => !!a && typeof a === 'object' && typeof (a as AlertObject).id === 'string');
  return uniqueAlerts(alerts).filter(a => alertRaisedAt(a) != null);
}

/** Oldest first, so the alerts raised by a moment are a prefix. */
export function sortByRaised(alerts: readonly AlertObject[]): AlertObject[] {
  return [...alerts].sort((a, b) => (alertRaisedAt(a) ?? 0) - (alertRaisedAt(b) ?? 0));
}

/** How many of `ascending` were raised at or before `at` (none without a playhead). */
export function countRaisedBy(ascending: readonly AlertObject[], at: number | null): number {
  if (at == null) return 0;
  let n = 0;
  while (n < ascending.length && (alertRaisedAt(ascending[n]) ?? Infinity) <= at) n += 1;
  return n;
}

interface Loaded { date: string; minute: number; alerts: AlertObject[]; loading: boolean; error: string | null }

const noSubscription = () => () => {};
const NONE: AlertObject[] = [];

export function useHodMomoReplay(): HodMomoReplay | null {
  const playhead = useSimPlayheadMinute();
  const date = playhead?.date ?? null;
  const minute = playhead?.minute ?? null;
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (date == null || minute == null) {
      setLoaded(null);
      return undefined;
    }
    const controller = new AbortController();
    let retry: number | undefined;
    // The same day's earlier list stays while this minute loads: the per-second
    // filter below keeps anything after the playhead out of sight.
    setLoaded(prev => ({
      date, minute, alerts: prev?.date === date ? prev.alerts : NONE, loading: true, error: null,
    }));
    replayRequest<unknown>(hodMomoHistoryPath(date, boardMinuteEnd(minute)), { signal: controller.signal }, HOD_HISTORY_REQUEST_FAILED)
      .then((raw) => {
        if (controller.signal.aborted) return;
        try {
          setLoaded({ date, minute, alerts: sortByRaised(parseHodHistory(raw)), loading: false, error: null });
        } catch (error) {
          setLoaded({ date, minute, alerts: NONE, loading: false, error: error instanceof Error ? error.message : String(error) });
        }
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message = error instanceof Error ? error.message : String(error);
        setLoaded(prev => ({ date, minute, alerts: prev?.date === date ? prev.alerts : NONE, loading: false, error: message }));
        retry = window.setTimeout(() => setAttempt(n => n + 1), LEADERBOARD_PLAYBACK_RETRY_MS);
      });
    return () => {
      controller.abort();
      window.clearTimeout(retry);
    };
  }, [date, minute, attempt]);

  const ascending = loaded && loaded.date === date ? loaded.alerts : NONE;
  const sim = useSimVenue();
  const active = date != null;
  const subscribe = useCallback(
    (listener: () => void) => (sim && active ? simClockResource.subscribe(listener) : noSubscription()),
    [sim, active],
  );
  const count = useSyncExternalStore(
    subscribe,
    () => countRaisedBy(ascending, playheadSecond(simClockResource.getSnapshot().data)),
  );
  const alerts = useMemo(() => ascending.slice(0, count).reverse(), [ascending, count]);
  const loading = !loaded || loaded.date !== date || loaded.minute !== minute || loaded.loading;
  const error = loaded && loaded.date === date ? loaded.error : null;
  const state = useMemo<HodMomoReplayState | null>(
    () => (date != null && minute != null ? { date, minute, loading, error } : null),
    [date, minute, loading, error],
  );
  return useMemo(() => (state ? { state, alerts } : null), [state, alerts]);
}
