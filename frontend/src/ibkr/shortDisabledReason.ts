/**
 * Why the ticket's Short segment is refused right now, or null when it may open a short (ADR 009, ADR 048).
 *
 * Paper and Sim take shorts through the one short check with no Live key (ADR 048 step 2), and the ticket
 * now carries the Buy stop every short goes out with, so nothing here locks them: the SHORT CHECK box shows
 * the venue's own borrow, SSR and margin, and the execution door decides. On Sim off the live edge today's
 * listing would be the wrong day's borrow anyway. Live keeps its locks: IBKR_SHORT_ENABLED, then a fresh,
 * shortable listing.
 */
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
  /** The desk venue: Paper and Sim short on their own ledger, with no Live key (ADR 048). */
  mode?: IbkrMode | null,
): string | null {
  if (mode === 'paper' || mode === 'sim') return null;
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
