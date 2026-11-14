/**
 * The desk's positions lists read every book (ADR 072): hand in your rows, get yours and the other traders'.
 *
 * Paper and Sim. Live and the sample desk hand your rows back as they came, and ask for nothing: the practice
 * account is one shared poll per venue (`practiceAccountResource`), so a reader there adds no request either. For
 * reading only: every Sell, Flatten, Cover, hotkey and the ticket keep your rows (`deskPositions`).
 */
import { useMemo } from 'react';
import { usePracticeAccount } from '../practice';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import { useSampleRoute } from '../sample_data/useSampleRoute';
import { deskPositions, othersBook, type DeskPosition, type OwnerHold } from './deskPositions';
import { deskVenueOf, isPracticeDeskVenue } from './deskVenue';
import type { IbkrPosition } from './types';
import { useIbkrStatus } from './useIbkrStatus';

export interface DeskPositionsView {
  rows: DeskPosition[];
  /** Each stock's other traders and their shares, signed, the biggest first; empty on Live. */
  othersBook: ReadonlyMap<string, readonly OwnerHold[]>;
  /** The last read of the other traders' shares failed: their rows are the last known, or missing. */
  othersStale: boolean;
  /** True while the rows say whose they are: Paper and Sim, with their books. */
  split: boolean;
}

const NO_ROWS: IbkrPosition[] = [];

export function useDeskPositions(yours: IbkrPosition[] = NO_ROWS): DeskPositionsView {
  // Both, read every render: the header sits above the sample provider and knows the sample desk by its route.
  const sampleData = useSampleDataOptional();
  const sampleRoute = useSampleRoute();
  const venue = deskVenueOf(useIbkrStatus());
  const practice = usePracticeAccount(!sampleData && !sampleRoute && isPracticeDeskVenue(venue) ? venue : null);
  const account = practice.data;
  const stale = practice.error != null || practice.stale === true;
  return useMemo(
    () => ({
      rows: deskPositions(yours, account),
      othersBook: othersBook(account),
      othersStale: stale,
      split: account?.books != null,
    }),
    [yours, account, stale],
  );
}

/** The other trader holding the most shares in one stock, signed; null on Live and while nobody else holds it. */
export function useOthersHold(symbol: string | null | undefined): OwnerHold | null {
  const { othersBook: book } = useDeskPositions();
  return book.get(symbol?.trim().toUpperCase() ?? '')?.[0] ?? null;
}
