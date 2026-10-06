/**
 * Backend-confirmed venue transitions, shared across desk windows (ADR 042).
 * Owns nova.desk.poll.snap.confirmed-venue, schema 1. A transition invalidates
 * its generation. Persisted rows only order/synchronize confirmations; they
 * never hydrate backend authority. Received live shares expire after the desk
 * share TTL. The successful status/venue routes are the only local writers.
 */
import {
  DESK_POLL_CONFIRMED_VENUE_SHARE,
  DESK_POLL_SNAPSHOT_MAX_AGE_MS,
} from '../constantGroups/global_bar';
import type { DeskVenue } from '../constantGroups/desk_venue';
import { isSampleView } from '../sample_data/sampleNav';
import {
  deskPollOwnerId,
  publishDeskPollSnap,
  readDeskPollSnap,
  subscribeDeskPollSnap,
  type DeskPollEnvelope,
} from './deskSharedPoll';
import { explicitVenueOf } from './deskVenue';

export interface ConfirmedDeskVenueSnapshot {
  venue: DeskVenue | null;
  generation: string | null;
}

interface VenueSignal extends ConfirmedDeskVenueSnapshot {
  schema_version: 1;
  revision: number;
}

export const UNKNOWN_CONFIRMED_DESK_VENUE: ConfirmedDeskVenueSnapshot = {
  venue: null, generation: null,
};

let snapshot = UNKNOWN_CONFIRMED_DESK_VENUE;
let revision = 0;
let tokenSerial = 0;
const listeners = new Set<() => void>();
let shareUnsub: (() => void) | null = null;

function signal(raw: unknown): VenueSignal | null {
  if (!raw || typeof raw !== 'object') return null;
  const row = raw as VenueSignal;
  if (row.schema_version !== 1) {
    console.warn('[Nova] refusing unknown confirmed venue signal schema', row.schema_version);
    return null;
  }
  if (!Number.isSafeInteger(row.revision) || row.revision <= 0) return null;
  const venue = explicitVenueOf({ venue: row.venue ?? undefined });
  if (row.venue !== null && venue === null) return null;
  if (venue ? typeof row.generation !== 'string' || !row.generation : row.generation !== null) return null;
  return { schema_version: 1, venue, generation: row.generation, revision: row.revision };
}

function latestSignal(): DeskPollEnvelope<VenueSignal> | null {
  const env = readDeskPollSnap<unknown>(DESK_POLL_CONFIRMED_VENUE_SHARE);
  const row = signal(env?.payload);
  return env && row ? { ts: env.ts, payload: row } : null;
}

function adopt(row: VenueSignal): void {
  revision = row.revision;
  if (snapshot.venue === row.venue && snapshot.generation === row.generation) return;
  snapshot = { venue: row.venue, generation: row.generation };
  listeners.forEach((listener) => listener());
}

function fresh(env: DeskPollEnvelope<unknown>): boolean {
  const age = Date.now() - env.ts;
  return age >= 0 && age <= DESK_POLL_SNAPSHOT_MAX_AGE_MS;
}

export function getConfirmedDeskVenueStoreSnapshot(): ConfirmedDeskVenueSnapshot {
  return snapshot;
}

/** Metadata can fence a late request even before its storage event is delivered. */
export function getConfirmedDeskVenueRevision(): number {
  return Math.max(revision, latestSignal()?.payload.revision ?? 0);
}

export function isConfirmedDeskVenueStoreSnapshotCurrent(asked: ConfirmedDeskVenueSnapshot): boolean {
  const latest = latestSignal()?.payload;
  return asked.venue === snapshot.venue && asked.generation === snapshot.generation
    && (!latest || latest.revision <= revision || latest.generation === asked.generation);
}

/** Use only a successful backend answer's explicit venue; null never means Live. */
export function confirmDeskVenue(value: unknown): void {
  if (isSampleView()) return;
  const venue = explicitVenueOf({ venue: value } as { venue?: DeskVenue });
  const latest = latestSignal();
  if (latest && fresh(latest) && latest.payload.venue === venue && latest.payload.revision >= revision) {
    adopt(latest.payload);
  } else if (snapshot.venue !== venue || (venue !== null && snapshot.generation === null)
    || (latest?.payload.revision ?? 0) > revision) {
    const nextRevision = Math.max(Date.now(), getConfirmedDeskVenueRevision() + 1);
    tokenSerial += 1;
    adopt({
      schema_version: 1,
      venue,
      generation: venue ? `${deskPollOwnerId()}:${nextRevision}:${tokenSerial}` : null,
      revision: nextRevision,
    });
  }
  if (revision > 0) {
    publishDeskPollSnap<VenueSignal>(DESK_POLL_CONFIRMED_VENUE_SHARE, {
      schema_version: 1, ...snapshot, revision,
    });
  }
}

export function subscribeConfirmedDeskVenueStore(listener: () => void): () => void {
  listeners.add(listener);
  if (!shareUnsub) {
    // subscribeDeskPollSnap also reads storage synchronously. That cached row
    // supplies ordering metadata only; a real cross-window event supplies authority.
    let listening = false;
    shareUnsub = subscribeDeskPollSnap<unknown>(DESK_POLL_CONFIRMED_VENUE_SHARE, (env) => {
      if (!listening || !fresh(env)) return;
      const row = signal(env.payload);
      if (row && row.revision > revision) adopt(row);
    });
    listening = true;
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) {
      shareUnsub?.();
      shareUnsub = null;
    }
  };
}

export function _resetConfirmedDeskVenueStoreForTests(): void {
  shareUnsub?.();
  shareUnsub = null;
  listeners.clear();
  snapshot = UNKNOWN_CONFIRMED_DESK_VENUE;
  revision = 0;
  tokenSerial = 0;
}
