/**
 * One shared history poll per (venue, range) for the Account page.
 *
 * Subscribers exist only while the desk venue is Paper or Sim -- the hook
 * subscribes to nothing on Live, so no request is made where there is no
 * practice ledger and the page can state the absence without guessing.
 */
import { useCallback, useSyncExternalStore } from 'react';
import {
  ACCOUNT_HISTORY_POLL_MS,
  ACCOUNT_HISTORY_UNREADABLE,
  accountHistoryPath,
  type AccountRange,
} from '../constantGroups/account_page';
import type { PracticeVenue } from '../constantGroups/practice';
import { isPracticeVenue } from '../practice/practiceAccountModel';
import { replayPollResource, type ReplayResourceState } from '../sim/replayPollResource';
import type { PracticeHistory } from './accountHistoryTypes';

type HistoryResource = ReturnType<typeof replayPollResource<PracticeHistory>>;

const resources = new Map<string, HistoryResource>();
const keyOf = (venue: PracticeVenue, range: AccountRange): string => `${venue}:${range}`;

export function accountHistoryResource(venue: PracticeVenue, range: AccountRange): HistoryResource {
  const key = keyOf(venue, range);
  let resource = resources.get(key);
  if (!resource) {
    resource = replayPollResource<PracticeHistory>(
      accountHistoryPath(venue, range),
      () => ACCOUNT_HISTORY_POLL_MS,
    );
    resources.set(key, resource);
  }
  return resource;
}

const IDLE: ReplayResourceState<PracticeHistory> = { data: null, error: null };
const idleSnapshot = () => IDLE;
const noop = () => {};

type Loose = Record<string, unknown>;
const isObject = (value: unknown): value is Loose =>
  value != null && typeof value === 'object' && !Array.isArray(value);
const rows = <T,>(value: unknown): T[] => (Array.isArray(value) ? (value.filter(isObject) as T[]) : []);

/**
 * The history the panels can render (QA C11): every list a list of rows, so
 * `daily: null` can no longer replace the Account page. `components` is the
 * money itself -- when it is missing the answer is unreadable, never zeros.
 */
export function normalizePracticeHistory(raw: unknown): PracticeHistory | null {
  if (!isObject(raw) || !isObject(raw.components)) return null;
  return {
    ...(raw as unknown as PracticeHistory),
    equity: rows(raw.equity),
    fills: rows(raw.fills),
    by_source: rows(raw.by_source),
    daily: rows(raw.daily),
    archives: rows(raw.archives),
    warnings: Array.isArray(raw.warnings) ? raw.warnings.filter((w): w is string => typeof w === 'string') : [],
  };
}

const normalized = new WeakMap<ReplayResourceState<PracticeHistory>, ReplayResourceState<PracticeHistory>>();

/** One normalised snapshot per published state, so useSyncExternalStore sees a stable value. */
function normalizedState(state: ReplayResourceState<PracticeHistory>): ReplayResourceState<PracticeHistory> {
  if (state.data == null) return state;
  let out = normalized.get(state);
  if (!out) {
    const data = normalizePracticeHistory(state.data);
    out = data
      ? { data, error: state.error }
      : { data: null, error: state.error ?? ACCOUNT_HISTORY_UNREADABLE };
    normalized.set(state, out);
  }
  return out;
}

/** The ledger history for `venue` + `range`, or an idle state off the practice venues. */
export function useAccountHistory(
  venue: string | null | undefined,
  range: AccountRange,
): ReplayResourceState<PracticeHistory> {
  const resource = isPracticeVenue(venue) ? accountHistoryResource(venue, range) : null;
  const subscribe = useCallback(
    (listener: () => void) => (resource ? resource.subscribe(listener) : noop),
    [resource],
  );
  const getSnapshot = useCallback(
    () => (resource ? normalizedState(resource.getSnapshot()) : IDLE),
    [resource],
  );
  return useSyncExternalStore(subscribe, resource ? getSnapshot : idleSnapshot);
}

/** After a reset every cached range for the venue refetches at once. */
export function invalidateAccountHistory(venue: PracticeVenue): void {
  const prefix = `${venue}:`;
  resources.forEach((resource, key) => {
    if (key.startsWith(prefix)) resource.invalidate();
  });
}

/** Test helper. */
export function resetAccountHistoryResourcesForTests(): void {
  resources.clear();
}
