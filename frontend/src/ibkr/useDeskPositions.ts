/**
 * The desk's positions lists read both books (ADR 069 decision 9): hand in your rows, get yours and the bots'.
 *
 * Paper only. Live, Sim and the sample desk hand your rows back as they came, and ask for nothing: the practice
 * account is one shared poll (`practiceAccountResource`), so a reader on Paper adds no request either. For reading
 * only: every Sell, Flatten, Cover, hotkey and the ticket keep your rows (`deskPositions`).
 */
import { useMemo } from 'react';
import { usePracticeAccount } from '../practice';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import { useSampleRoute } from '../sample_data/useSampleRoute';
import { botsBook, deskPositions, type DeskPosition } from './deskPositions';
import { deskVenueOf } from './deskVenue';
import type { IbkrPosition } from './types';
import { useIbkrStatus } from './useIbkrStatus';

export interface DeskPositionsView {
  rows: DeskPosition[];
  /** Every bot's shares per stock, signed; empty off Paper. */
  botsBook: ReadonlyMap<string, number>;
  /** The last read of the bots' shares failed: their rows are the last known, or missing. */
  botsStale: boolean;
  /** True while the rows say whose they are: Paper with its two books. */
  split: boolean;
}

const NO_ROWS: IbkrPosition[] = [];

export function useDeskPositions(yours: IbkrPosition[] = NO_ROWS): DeskPositionsView {
  // Both, read every render: the header sits above the sample provider and knows the sample desk by its route.
  const sampleData = useSampleDataOptional();
  const sampleRoute = useSampleRoute();
  const venue = deskVenueOf(useIbkrStatus());
  const practice = usePracticeAccount(!sampleData && !sampleRoute && venue === 'paper' ? 'paper' : null);
  const account = practice.data;
  const stale = practice.error != null || practice.stale === true;
  return useMemo(
    () => ({
      rows: deskPositions(yours, account),
      botsBook: botsBook(account),
      botsStale: stale,
      split: account?.books != null,
    }),
    [yours, account, stale],
  );
}

/** The bots' shares in one stock, signed; 0 off Paper and while they hold none. */
export function useBotsQty(symbol: string | null | undefined): number {
  const { botsBook: book } = useDeskPositions();
  return book.get(symbol?.trim().toUpperCase() ?? '') ?? 0;
}
