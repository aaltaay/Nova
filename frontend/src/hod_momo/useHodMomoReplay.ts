/**
 * The HOD Momo strip at the Sim playhead (ADR 023, "one desk, one clock").
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
import {
  HOD_HISTORY_REQUEST_FAILED,
  HOD_REBUILD_ASK_AGAIN_MS,
  HOD_REBUILD_POLL_MS,
  HOD_REBUILD_REQUEST_FAILED,
  LEADERBOARD_PLAYBACK_RETRY_MS,
  hodMomoHistoryPath,
  hodMomoRebuildPath,
} from '../leaderboard/leaderboardConstants';
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
  /**
   * False: Nova kept no HOD Momo record of the day (the history route's `recorded`), so
   * the strip states that absence instead of "No alerts raised". Null until the first
   * read answers, or from an older backend's bare list, which never said.
   */
  recorded: boolean | null;
  /** `rebuilt`: the alerts are the day's rebuild (Nova kept no record); `recorded`: Nova's own; null: none to show. */
  source: HodHistorySource;
  /** Where the rebuild of a day with no record is (null on a recorded day, or before the first read answers). */
  rebuild: HodRebuildState | null;
}

export type HodHistorySource = 'recorded' | 'rebuilt' | null;

/** The history route's `rebuild`: the rebuild job's state, or why there is none. */
export interface HodRebuildState {
  status: string;
  reason: string | null;
  stage: string | null;
  done: number | null;
  total: number | null;
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

/** The history body's alerts: `{alerts: [...]}`, or an older backend's bare list. Undated alerts are left out. */
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

const text = (v: unknown): string | null => (typeof v === 'string' && v ? v : null);
const count = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);

/** The body's `rebuild`, or null when it has none (a recorded day, an older backend). */
export function parseHodRebuild(raw: unknown): HodRebuildState | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
  const r = raw as Record<string, unknown>;
  const status = text(r.status);
  if (!status) return null;
  return { status, reason: text(r.reason), stage: text(r.stage), done: count(r.done), total: count(r.total), error: text(r.error) };
}

export interface HodHistoryDay {
  recorded: boolean | null;
  source: HodHistorySource;
  rebuild: HodRebuildState | null;
  alerts: AlertObject[];
}

/**
 * The history body `{date, recorded, source, alerts, error, rebuild}`: whether Nova kept a HOD Momo
 * record of the day (null from a bare list), where the alerts come from, and the rebuild's state. A
 * snapshot on file that could not be read (`error`) throws, so the strip says it did not load rather
 * than "No alerts raised".
 */
export function parseHodHistoryDay(raw: unknown): HodHistoryDay {
  const body = raw && typeof raw === 'object' && !Array.isArray(raw)
    ? raw as { recorded?: unknown; error?: unknown; source?: unknown; rebuild?: unknown }
    : null;
  if (body && typeof body.error === 'string' && body.error) throw new Error(body.error);
  const source = body?.source === 'recorded' || body?.source === 'rebuilt' ? body.source : null;
  return {
    recorded: typeof body?.recorded === 'boolean' ? body.recorded : null,
    source,
    rebuild: parseHodRebuild(body?.rebuild),
    alerts: parseHodHistory(raw),
  };
}

/** A rebuild that should be asked for: never asked, out of date, or stopped before it finished. */
export function rebuildWanted(rebuild: HodRebuildState | null): boolean {
  return rebuild != null && (rebuild.status === 'none' || rebuild.status === 'stopped');
}

/** A rebuild still running: its state is read again until it ends. */
export function rebuildRunning(rebuild: HodRebuildState | null): boolean {
  return rebuild != null && (rebuild.status === 'queued' || rebuild.status === 'building');
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

interface Loaded {
  date: string; minute: number; alerts: AlertObject[]; recorded: boolean | null; loading: boolean; error: string | null;
  source: HodHistorySource; rebuild: HodRebuildState | null;
}

const noSubscription = () => () => {};
// When each day's rebuild was last asked for: every strip shares one ask.
const lastAsked = new Map<string, number>();
const askedAt = (date: string): number => lastAsked.get(date) ?? 0;

export function resetHodRebuildAsksForTests(): void {
  lastAsked.clear();
}
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
      date,
      minute,
      alerts: prev?.date === date ? prev.alerts : NONE,
      recorded: prev?.date === date ? prev.recorded : null,
      source: prev?.date === date ? prev.source : null,
      rebuild: prev?.date === date ? prev.rebuild : null,
      loading: true,
      error: null,
    }));
    replayRequest<unknown>(hodMomoHistoryPath(date, boardMinuteEnd(minute)), { signal: controller.signal }, HOD_HISTORY_REQUEST_FAILED)
      .then((raw) => {
        if (controller.signal.aborted) return;
        try {
          const day = parseHodHistoryDay(raw);
          setLoaded({
            date, minute, alerts: sortByRaised(day.alerts), recorded: day.recorded, source: day.source,
            rebuild: day.rebuild, loading: false, error: null,
          });
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error);
          setLoaded({ date, minute, alerts: NONE, recorded: null, source: null, rebuild: null, loading: false, error: message });
        }
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message = error instanceof Error ? error.message : String(error);
        setLoaded(prev => ({
          date,
          minute,
          alerts: prev?.date === date ? prev.alerts : NONE,
          recorded: prev?.date === date ? prev.recorded : null,
          source: prev?.date === date ? prev.source : null,
          rebuild: prev?.date === date ? prev.rebuild : null,
          loading: false,
          error: message,
        }));
        retry = window.setTimeout(() => setAttempt(n => n + 1), LEADERBOARD_PLAYBACK_RETRY_MS);
      });
    return () => {
      controller.abort();
      window.clearTimeout(retry);
    };
  }, [date, minute, attempt]);

  // A day with no record: ask for its rebuild, and read the history again while it runs.
  const rebuild = loaded && loaded.date === date && !loaded.loading ? loaded.rebuild : null;
  const wanted = rebuildWanted(rebuild);
  const running = rebuildRunning(rebuild);
  useEffect(() => {
    if (date == null || (!wanted && !running)) return undefined;
    const controller = new AbortController();
    let timer: number | undefined;
    if (wanted && askedAt(date) + HOD_REBUILD_ASK_AGAIN_MS <= Date.now()) {
      lastAsked.set(date, Date.now());
      replayRequest<unknown>(hodMomoRebuildPath(date), { method: 'POST', signal: controller.signal }, HOD_REBUILD_REQUEST_FAILED)
        .then((raw) => {
          if (controller.signal.aborted) return;
          const answer = parseHodRebuild(raw);
          if (answer && (answer.status === 'unavailable' || answer.status === 'failed')) {
            // Final: say why, and ask no more (the history read may not know it yet).
            setLoaded(prev => (prev && prev.date === date ? { ...prev, rebuild: answer } : prev));
            return;
          }
          setAttempt(n => n + 1);
        })
        .catch(() => {                     // a failed ask is asked again once the next read still wants it
          if (!controller.signal.aborted) setAttempt(n => n + 1);
        });
    } else {
      timer = window.setTimeout(() => setAttempt(n => n + 1), wanted ? HOD_REBUILD_ASK_AGAIN_MS : HOD_REBUILD_POLL_MS);
    }
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [date, wanted, running, rebuild]);

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
  const recorded = loaded && loaded.date === date ? loaded.recorded : null;
  const source = loaded && loaded.date === date ? loaded.source : null;
  const shownRebuild = loaded && loaded.date === date ? loaded.rebuild : null;
  const state = useMemo<HodMomoReplayState | null>(
    () => (date != null && minute != null
      ? { date, minute, loading, error, recorded, source, rebuild: shownRebuild }
      : null),
    [date, minute, loading, error, recorded, source, shownRebuild],
  );
  return useMemo(() => (state ? { state, alerts } : null), [state, alerts]);
}
