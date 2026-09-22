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
  const getSnapshot = resource ? resource.getSnapshot : idleSnapshot;
  return useSyncExternalStore(subscribe, getSnapshot);
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
