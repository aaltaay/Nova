/** One confirmed venue source for mounted preferences, tickets and bot state. */
import { useSyncExternalStore } from 'react';
import type { DeskVenue } from '../constantGroups/desk_venue';
import { isSampleView } from '../sample_data/sampleNav';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import {
  getConfirmedDeskVenueStoreSnapshot,
  isConfirmedDeskVenueStoreSnapshotCurrent,
  subscribeConfirmedDeskVenueStore,
  UNKNOWN_CONFIRMED_DESK_VENUE,
  type ConfirmedDeskVenueSnapshot,
} from './confirmedDeskVenueStore';
import { subscribeIbkrStatus } from './ibkrStatusPoller';

export type { ConfirmedDeskVenueSnapshot };

export function getConfirmedDeskVenueSnapshot(): ConfirmedDeskVenueSnapshot {
  return isSampleView() ? UNKNOWN_CONFIRMED_DESK_VENUE : getConfirmedDeskVenueStoreSnapshot();
}

export function isConfirmedDeskVenueSnapshotCurrent(asked: ConfirmedDeskVenueSnapshot): boolean {
  return !isSampleView() && isConfirmedDeskVenueStoreSnapshotCurrent(asked);
}

export function subscribeConfirmedDeskVenue(listener: () => void): () => void {
  if (isSampleView()) return () => {};
  const offVenue = subscribeConfirmedDeskVenueStore(listener);
  // Subscribers reuse the status poller's single interval, not a new venue poll.
  const offStatus = subscribeIbkrStatus(listener);
  return () => { offVenue(); offStatus(); };
}

const unknownSnapshot = () => UNKNOWN_CONFIRMED_DESK_VENUE;
const noSubscription = () => () => {};

export function useConfirmedDeskVenue(): DeskVenue | null {
  const sample = useSampleDataOptional();
  return useSyncExternalStore(
    sample ? noSubscription : subscribeConfirmedDeskVenue,
    sample ? unknownSnapshot : getConfirmedDeskVenueSnapshot,
    unknownSnapshot,
  ).venue;
}
