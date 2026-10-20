/**
 * The Global page's switches -- the period and what the map's colour shows -- remembered on the desk (ADR 060).
 *
 * Owner: this module. Key `nova.globalBoard.prefs.v1`, shape `{schema_version: 1, period, color_by}`
 * (architecture/schema/global-board.md). Invalidation: an unknown schema_version, or a value that is not a known
 * period / colour, falls back to 1D / pressure for that field -- never migrated by guesswork. The sample desk never
 * writes it.
 */
import { useCallback, useState } from 'react';
import { GLOBAL_PERIODS, GLOBAL_PREFS_SCHEMA_VERSION, GLOBAL_PREFS_STORAGE_KEY } from './constants';
import type { ColorBy, Period } from './types';

export interface GlobalPrefs {
  period: Period;
  colorBy: ColorBy;
}

export const DEFAULT_PREFS: GlobalPrefs = { period: '1D', colorBy: 'pressure' };

export function parsePrefs(raw: unknown): GlobalPrefs {
  if (!raw || typeof raw !== 'object') return DEFAULT_PREFS;
  const r = raw as Record<string, unknown>;
  if (r.schema_version !== GLOBAL_PREFS_SCHEMA_VERSION) return DEFAULT_PREFS;
  return {
    period: (GLOBAL_PERIODS as readonly unknown[]).includes(r.period) ? (r.period as Period) : '1D',
    colorBy: r.color_by === 'move' ? 'move' : 'pressure',
  };
}

function readPrefs(): GlobalPrefs {
  try {
    const text = window.localStorage.getItem(GLOBAL_PREFS_STORAGE_KEY);
    return text ? parsePrefs(JSON.parse(text)) : DEFAULT_PREFS;
  } catch {
    return DEFAULT_PREFS; // storage blocked or the value unreadable: the defaults
  }
}

function writePrefs(p: GlobalPrefs): void {
  try {
    window.localStorage.setItem(
      GLOBAL_PREFS_STORAGE_KEY,
      JSON.stringify({ schema_version: GLOBAL_PREFS_SCHEMA_VERSION, period: p.period, color_by: p.colorBy }),
    );
  } catch {
    // storage blocked (private window, a quota): the switch still works for this session
  }
}

/** The page's switches and a setter that remembers them (`persist` false on the sample desk). */
export function useGlobalPrefs(persist: boolean): [GlobalPrefs, (next: GlobalPrefs) => void] {
  const [prefs, setPrefs] = useState<GlobalPrefs>(() => (persist ? readPrefs() : DEFAULT_PREFS));
  const set = useCallback(
    (next: GlobalPrefs) => {
      setPrefs(next);
      if (persist) writePrefs(next);
    },
    [persist],
  );
  return [prefs, set];
}
