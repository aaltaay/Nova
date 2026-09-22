/** Why the ticket's Short segment is refused right now, or null when it may open a short (ADR 009). */
import { PRACTICE_NO_SHORTS_REASON } from '../constantGroups/practice';
import {
  SHORTABILITY_NOT_SHORTABLE,
  SHORTABILITY_SHORT_DISABLED,
  SHORTABILITY_STALE,
} from '../constantGroups/shortability';
import type { IbkrListingFlags } from '../types/ticker';
import { resolveShortabilityState } from './ShortabilityChip';
import type { IbkrMode } from './types';

export function shortDisabledReason(
  shortEnabled: boolean | undefined,
  listing: IbkrListingFlags | null | undefined,
  /** The desk venue. Paper and Sim refuse every short entry (`PRACTICE_NO_SHORTS`). */
  mode?: IbkrMode | null,
): string | null {
  // The practice broker never shorts, whatever the listing or TWS says -- the
  // reason is Nova's, not the symbol's (QA 2026-09-22, V13).
  if (mode === 'paper' || mode === 'sim') return PRACTICE_NO_SHORTS_REASON;
  if (!shortEnabled) return SHORTABILITY_SHORT_DISABLED;
  if (!listing) return SHORTABILITY_NOT_SHORTABLE;
  if (listing.stale) return SHORTABILITY_STALE;
  const state = resolveShortabilityState(listing);
  // Explicit false only — missing orderable (legacy payloads) still OK when state is est.
  if (state !== 'shortable_est' || listing.orderable === false) {
    return SHORTABILITY_NOT_SHORTABLE;
  }
  return null;
}
