/**
 * One shared practice-account poll per venue (ADR 020).
 *
 * Subscribers exist only while the desk venue is Paper or Sim -- the hook
 * subscribes to nothing otherwise, so no request is made off the practice
 * venues and the strip can render nothing without guessing.
 */
import { useCallback, useSyncExternalStore } from 'react';
import {
  PRACTICE_ACCOUNT_POLL_MS,
  PRACTICE_RESET_API_PATH,
  practiceAccountPath,
  type PracticeVenue,
} from '../constantGroups/practice';
import { replayPollResource, type ReplayResourceState } from '../sim/replayPollResource';
import { replayPost, replayRequest } from '../sim/replayRequest';
import { isPracticeVenue } from './practiceAccountModel';
import type { PracticeAccount } from './practiceTypes';

const resources = {
  paper: replayPollResource<PracticeAccount>(practiceAccountPath('paper'), () => PRACTICE_ACCOUNT_POLL_MS),
  sim: replayPollResource<PracticeAccount>(practiceAccountPath('sim'), () => PRACTICE_ACCOUNT_POLL_MS),
} as const;

export const practiceAccountResource = (venue: PracticeVenue) => resources[venue];

const IDLE: ReplayResourceState<PracticeAccount> = { data: null, error: null };
const idleSnapshot = () => IDLE;
const noop = () => {};

/** The practice account for `venue`, or an idle state off the practice venues. */
export function usePracticeAccount(venue: string | null | undefined): ReplayResourceState<PracticeAccount> {
  const practice = isPracticeVenue(venue) ? venue : null;
  const subscribe = useCallback(
    (listener: () => void) => (practice ? resources[practice].subscribe(listener) : noop),
    [practice],
  );
  const getSnapshot = practice ? resources[practice].getSnapshot : idleSnapshot;
  return useSyncExternalStore(subscribe, getSnapshot);
}

/** POST /api/practice/reset; the answer replaces the venue's snapshot at once. */
export async function resetPracticeAccount(
  venue: PracticeVenue,
  startingCash: number | null,
): Promise<PracticeAccount> {
  const resource = resources[venue];
  resource.suspend();
  try {
    const body = startingCash == null ? { venue } : { venue, starting_cash: startingCash };
    const account = await replayRequest<PracticeAccount>(
      PRACTICE_RESET_API_PATH,
      replayPost(body),
      'Practice account reset failed',
    );
    resource.setData(account);
    return account;
  } finally {
    resource.resume();
  }
}
