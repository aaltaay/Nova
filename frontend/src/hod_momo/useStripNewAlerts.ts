/**
 * Which alerts arrived while this strip was mounted. The first non-empty list
 * the hook sees is the day's snapshot (nothing in it is new); an id seen after
 * that is NEW for HOD_MOMO_STRIP_NEW_MS, then quietly stops being new.
 */
import { useEffect, useReducer, useRef } from 'react';
import { HOD_MOMO_STRIP_NEW_MS } from './hodMomoStripConstants';
import type { AlertObject } from './types';
import { alertIdentity } from './hodMomoWire';

export function useStripNewAlerts(
  alerts: readonly AlertObject[],
  now: () => number = Date.now,
): ReadonlySet<string> {
  const seen = useRef<Map<string, number> | null>(null);
  const [, tick] = useReducer((n: number) => n + 1, 0);

  const at = now();
  if (seen.current === null) {
    if (alerts.length > 0) seen.current = new Map(alerts.map((a) => [alertIdentity(a), 0]));
  } else {
    for (const a of alerts) {
      const key = alertIdentity(a);
      if (!seen.current.has(key)) seen.current.set(key, at);
    }
  }

  const fresh = new Set<string>();
  let nextExpiry = Infinity;
  if (seen.current) {
    for (const a of alerts) {
      const key = alertIdentity(a);
      const ts = seen.current.get(key) ?? 0;
      if (ts > 0 && at - ts < HOD_MOMO_STRIP_NEW_MS) {
        fresh.add(key);
        nextExpiry = Math.min(nextExpiry, ts + HOD_MOMO_STRIP_NEW_MS);
      }
    }
  }

  useEffect(() => {
    if (!Number.isFinite(nextExpiry)) return undefined;
    const id = window.setTimeout(tick, Math.max(0, nextExpiry - now()) + 1);
    return () => window.clearTimeout(id);
  }, [nextExpiry, now]);

  return fresh;
}
