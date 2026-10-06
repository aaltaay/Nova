/**
 * Which days the operator's Massive flat files cover (ADR 046), shared by the
 * Sim Day calendar, the Sim tab prompt and the replay's Level 2 note.
 *
 * `GET /api/sim/history/massive/days` lists every day whose files are whole on
 * disk. It changes only as the downloader finishes a day, so it is read when a
 * reader mounts (at most once per `MASSIVE_DAYS_FRESH_MS`) and whenever the
 * calendar opens -- never polled. A failed read keeps the last good list and
 * says why; until one succeeds every day reads as not on disk, never guessed.
 */
import { useCallback, useEffect, useSyncExternalStore } from 'react';
import { replayRequest } from './replayRequest';
import { parseMassiveDays } from './simPayloadParse';
import type { MassiveDay, MassiveDays } from './historicalTypes';

export const MASSIVE_DAYS_PATH = '/history/massive/days';
export const MASSIVE_DAYS_FRESH_MS = 60_000;
const FAILURE = 'Could not read the Massive day list';

export interface MassiveDaysState {
  data: MassiveDays | null;
  /** `date -> day`, built once per answer. */
  byDate: ReadonlyMap<string, MassiveDay>;
  error: string | null;
}

const EMPTY: MassiveDaysState = { data: null, byDate: new Map(), error: null };
let state: MassiveDaysState = EMPTY;
let fetchedAt = 0;
let inflight: Promise<void> | null = null;
const listeners = new Set<() => void>();

function publish(next: MassiveDaysState) {
  state = next;
  listeners.forEach(listener => listener());
}

/** Read the list again when it is stale (or `force`); one request at a time. */
export function refreshMassiveDays(force = false): Promise<void> {
  if (inflight) return inflight;
  if (!force && state.data && Date.now() - fetchedAt < MASSIVE_DAYS_FRESH_MS) return Promise.resolve();
  inflight = replayRequest<unknown>(MASSIVE_DAYS_PATH, {}, FAILURE)
    .then(raw => {
      const data = parseMassiveDays(raw);
      fetchedAt = Date.now();
      publish({ data, byDate: new Map(data.days.map(day => [day.date, day])), error: null });
    })
    .catch((error: unknown) => {
      publish({ ...state, error: error instanceof Error ? error.message : String(error) });
    })
    .finally(() => { inflight = null; });
  return inflight;
}

export const massiveDays = {
  getSnapshot: () => state,
  subscribe(listener: () => void) {
    listeners.add(listener);
    return () => { listeners.delete(listener); };
  },
};

/** The list, read when `active` and kept fresh while a reader is mounted. */
export function useMassiveDays(active: boolean): MassiveDaysState & { refresh: () => void } {
  const subscribe = useCallback(
    (listener: () => void) => (active ? massiveDays.subscribe(listener) : () => {}),
    [active],
  );
  const current = useSyncExternalStore(subscribe, massiveDays.getSnapshot);
  useEffect(() => { if (active) void refreshMassiveDays(); }, [active]);
  const refresh = useCallback(() => { void refreshMassiveDays(true); }, []);
  return { ...(active ? current : EMPTY), refresh };
}

/** One day's files, or null when the day is not on disk (or the list is not read yet). */
export function useMassiveDay(date: string | null | undefined, active: boolean): MassiveDay | null {
  const { byDate } = useMassiveDays(active && Boolean(date));
  return date ? byDate.get(date) ?? null : null;
}

/** Test seam: the list is module state. */
export function resetMassiveDaysForTests(): void {
  state = EMPTY;
  fetchedAt = 0;
  inflight = null;
  listeners.clear();
}

/** Test seam: a list as if just read, so no reader asks the API for it. */
export function setMassiveDaysForTests(data: MassiveDays): void {
  fetchedAt = Date.now();
  publish({ data, byDate: new Map(data.days.map(day => [day.date, day])), error: null });
}
