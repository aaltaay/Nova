/** Why the ticket's Short segment is refused right now, or null when it may open a short (ADR 009). */
import { PRACTICE_TICKET_SHORT_LOCKED } from '../constantGroups/practice';
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
  /** The desk venue. On Paper and Sim the ticket's Short waits on its Buy stop (ADR 048). */
  mode?: IbkrMode | null,
): string | null {
  // The practice venues take shorts as a bracket with a buy stop (ADR 048); the ticket has no Buy
  // stop field yet, so its Short stays locked there whatever the listing says -- the reason is
  // Nova's, not the symbol's (QA 2026-09-22, V13).
  if (mode === 'paper' || mode === 'sim') return PRACTICE_TICKET_SHORT_LOCKED;
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
