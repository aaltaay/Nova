/**
 * The Congress page's switches and the members the operator follows, remembered on the desk (ADR 066).
 *
 * Owner: this module. Key `nova.congress.prefs.v1`, shape `{schema_version: 1, seats_period, traded_period,
 * following: [bioguide]}` (architecture/schema/congress.md). Invalidation: an unknown schema_version, or a value that
 * is not a known period or a bioguide id, falls back to `ytd` / none for that field -- never migrated by guesswork.
 * The sample desk never writes it.
 */
import { useCallback, useState } from 'react';
import { CONGRESS_PREFS_SCHEMA_VERSION, CONGRESS_PREFS_STORAGE_KEY, PERIODS } from './constants';
import type { Period } from './types';

export interface CongressPrefs {
  seatsPeriod: Period;
  tradedPeriod: Period;
  following: string[];
}

export const DEFAULT_PREFS: CongressPrefs = { seatsPeriod: 'ytd', tradedPeriod: 'ytd', following: [] };
const BIOGUIDE = /^[A-Z][0-9]{6}$/;

function period(v: unknown): Period {
  return (PERIODS as readonly unknown[]).includes(v) ? (v as Period) : 'ytd';
}

export function parsePrefs(raw: unknown): CongressPrefs {
  if (!raw || typeof raw !== 'object') return DEFAULT_PREFS;
  const r = raw as Record<string, unknown>;
  if (r.schema_version !== CONGRESS_PREFS_SCHEMA_VERSION) return DEFAULT_PREFS;
  const following = Array.isArray(r.following)
    ? [...new Set(r.following.filter((b): b is string => typeof b === 'string' && BIOGUIDE.test(b)))]
    : [];
  return { seatsPeriod: period(r.seats_period), tradedPeriod: period(r.traded_period), following };
}

function readPrefs(): CongressPrefs {
  try {
    const text = window.localStorage.getItem(CONGRESS_PREFS_STORAGE_KEY);
    return text ? parsePrefs(JSON.parse(text)) : DEFAULT_PREFS;
  } catch {
    return DEFAULT_PREFS; // storage blocked or the value unreadable: the defaults
  }
}

function writePrefs(p: CongressPrefs): void {
  try {
    window.localStorage.setItem(
      CONGRESS_PREFS_STORAGE_KEY,
      JSON.stringify({
        schema_version: CONGRESS_PREFS_SCHEMA_VERSION,
        seats_period: p.seatsPeriod,
        traded_period: p.tradedPeriod,
        following: p.following,
      }),
    );
  } catch {
    // storage blocked (private window, a quota): the switches still work for this session
  }
}

/** The page's switches and follows, and a setter that remembers them (`persist` false on the sample desk). */
export function useCongressPrefs(persist: boolean): [CongressPrefs, (next: CongressPrefs) => void] {
  const [prefs, setPrefs] = useState<CongressPrefs>(() => (persist ? readPrefs() : DEFAULT_PREFS));
  const set = useCallback(
    (next: CongressPrefs) => {
      setPrefs(next);
      if (persist) writePrefs(next);
    },
    [persist],
  );
  return [prefs, set];
}

export function toggleFollow(p: CongressPrefs, bioguide: string): CongressPrefs {
  const on = p.following.includes(bioguide);
  return { ...p, following: on ? p.following.filter((b) => b !== bioguide) : [...p.following, bioguide] };
}
