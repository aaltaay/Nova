/**
 * The Forex page's switches -- what the map and Follow the sun show, and the period -- remembered on the desk (ADR 062).
 *
 * Owner: this module. Key `nova.forexBoard.prefs.v1`, shape `{schema_version: 1, period, color_by}`
 * (architecture/schema/forex-board.md). Invalidation: an unknown schema_version, or a value that is not a known
 * period / colour, falls back to 1D / strength for that field -- never migrated by guesswork. The sample desk never
 * writes it.
 */
import { useCallback, useState } from 'react';
import { FOREX_PERIODS, FOREX_PREFS_SCHEMA_VERSION, FOREX_PREFS_STORAGE_KEY } from './constants';
import type { ColorBy, Period } from './types';

export interface ForexPrefs {
  period: Period;
  colorBy: ColorBy;
}

export const DEFAULT_PREFS: ForexPrefs = { period: '1D', colorBy: 'strength' };

export function parsePrefs(raw: unknown): ForexPrefs {
  if (!raw || typeof raw !== 'object') return DEFAULT_PREFS;
  const r = raw as Record<string, unknown>;
  if (r.schema_version !== FOREX_PREFS_SCHEMA_VERSION) return DEFAULT_PREFS;
  return {
    period: (FOREX_PERIODS as readonly unknown[]).includes(r.period) ? (r.period as Period) : '1D',
    colorBy: r.color_by === 'futures' ? 'futures' : 'strength',
  };
}

function readPrefs(): ForexPrefs {
  try {
    const text = window.localStorage.getItem(FOREX_PREFS_STORAGE_KEY);
    return text ? parsePrefs(JSON.parse(text)) : DEFAULT_PREFS;
  } catch {
    return DEFAULT_PREFS; // storage blocked or the value unreadable: the defaults
  }
}

function writePrefs(p: ForexPrefs): void {
  try {
    window.localStorage.setItem(
      FOREX_PREFS_STORAGE_KEY,
      JSON.stringify({ schema_version: FOREX_PREFS_SCHEMA_VERSION, period: p.period, color_by: p.colorBy }),
    );
  } catch {
    // storage blocked (private window, a quota): the switch still works for this session
  }
}

/** The page's switches and a setter that remembers them (`persist` false on the sample desk). */
export function useForexPrefs(persist: boolean): [ForexPrefs, (next: ForexPrefs) => void] {
  const [prefs, setPrefs] = useState<ForexPrefs>(() => (persist ? readPrefs() : DEFAULT_PREFS));
  const set = useCallback(
    (next: ForexPrefs) => {
      setPrefs(next);
      if (persist) writePrefs(next);
    },
    [persist],
  );
  return [prefs, set];
}
