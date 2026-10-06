/** Reactive defaults for an explicit confirmed venue, in this window and others. */
import { useMemo, useSyncExternalStore } from 'react';
import type { DeskVenue } from '../constantGroups/desk_venue';
import { readTradeDefaultsPrefs, subscribeTradeDefaultsPrefs, tradeDefaultsPrefsSnapshot } from './tradeDefaultsPrefs';

export function useTradeDefaultsPrefs(venue: DeskVenue | null) {
  const snapshot = useSyncExternalStore(
    subscribeTradeDefaultsPrefs,
    () => tradeDefaultsPrefsSnapshot(venue),
    () => '',
  );
  // The stable storage string invalidates the parsed value after writes/events.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(() => readTradeDefaultsPrefs(venue), [venue, snapshot]);
}
