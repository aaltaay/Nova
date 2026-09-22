/**
 * The desk venue from /api/ibkr/status (ADR 020; QA C26, 2026-09-22).
 *
 * `venue` is the one truth. `mode` equals it on Paper and Sim, but on Live it
 * is the Gateway port label -- `paper` on the by-hand legacy paper Gateway --
 * so reading `mode` as the venue showed Nova's NOVA-PAPER practice ledger on a
 * Live desk. `mode` is the fallback only for a backend that predates `venue`.
 */
import type { DeskVenue } from '../constantGroups/desk_venue';
import type { IbkrStatus } from './types';

const VENUES: readonly DeskVenue[] = ['live', 'paper', 'sim'];

function asVenue(value: unknown): DeskVenue | null {
  return typeof value === 'string' && (VENUES as readonly string[]).includes(value)
    ? (value as DeskVenue)
    : null;
}

/** `status.venue`, else `status.mode` when it names a venue, else null (disconnected, unknown). */
export function deskVenueOf(status: Pick<IbkrStatus, 'venue' | 'mode'> | null | undefined): DeskVenue | null {
  if (!status) return null;
  return asVenue(status.venue) ?? asVenue(status.mode);
}

/** Paper or Sim: Nova's practice ledger holds the account and orders. */
export function isPracticeDeskVenue(venue: DeskVenue | null | undefined): boolean {
  return venue === 'paper' || venue === 'sim';
}

/** Only the explicit ADR 020 `venue` field -- null when the backend did not state one. */
export function explicitVenueOf(status: Pick<IbkrStatus, 'venue'> | null | undefined): DeskVenue | null {
  return asVenue(status?.venue);
}

/**
 * True on Paper / Sim while the status itself is fresh: the practice ledger
 * serves account, positions and orders without IB Gateway (QA C68).
 */
export function practiceLedgerReachable(
  status: (Pick<IbkrStatus, 'venue' | 'mode'> & { stale?: boolean }) | null | undefined,
): boolean {
  const venue = deskVenueOf(status);
  return (venue === 'paper' || venue === 'sim') && status?.stale !== true;
}

/**
 * The venue a surface should follow: the status's own venue when it has one,
 * else the caller's legacy mode-as-venue value.
 */
export function resolveDeskVenue(
  status: Pick<IbkrStatus, 'venue' | 'mode'> | null | undefined,
  legacy: string | null | undefined,
): DeskVenue | null {
  return asVenue(status?.venue) ?? asVenue(legacy) ?? asVenue(status?.mode);
}
