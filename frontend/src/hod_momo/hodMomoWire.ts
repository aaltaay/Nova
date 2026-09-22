/**
 * Reading /ws/hod-momo frames honestly.
 *
 * QA C32: Python's `json.dumps` writes a bare `NaN` / `Infinity` token for a
 * non-finite float, which `JSON.parse` refuses -- one NaN in the `initial`
 * message dropped the whole day's alerts behind "No alerts yet" beside FEED
 * LIVE, and every reconnect dropped it again. The backend now scrubs those
 * values to null; this parser also reads an older backend's frame by turning
 * bare non-finite tokens (never text inside strings) into null, and says so
 * when a frame still cannot be read.
 *
 * Pure: no module state.
 */
import type { AlertObject } from './types';

export const HOD_FEED_UNREADABLE = "HOD feed payload unreadable -- today's alerts could not be read";

const TOKENS: ReadonlyArray<string> = ['-Infinity', 'Infinity', 'NaN'];

/** Replace bare NaN / Infinity / -Infinity tokens outside JSON strings with null. */
export function scrubNonFiniteTokens(text: string): string {
  const parts: string[] = [];
  let last = 0;
  let inString = false;
  let i = 0;
  while (i < text.length) {
    const ch = text.charCodeAt(i);
    if (inString) {
      if (ch === 92 /* \ */) {
        i += 2;
        continue;
      }
      if (ch === 34 /* " */) inString = false;
      i += 1;
      continue;
    }
    if (ch === 34) {
      inString = true;
      i += 1;
      continue;
    }
    if (ch === 45 /* - */ || ch === 73 /* I */ || ch === 78 /* N */) {
      const token = TOKENS.find((t) => text.startsWith(t, i));
      if (token) {
        parts.push(text.slice(last, i), 'null');
        i += token.length;
        last = i;
        continue;
      }
    }
    i += 1;
  }
  if (last === 0) return text;
  parts.push(text.slice(last));
  return parts.join('');
}

/** A parsed frame, or undefined when it cannot be read even after the scrub. */
export function parseHodFrame(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    try {
      return JSON.parse(scrubNonFiniteTokens(text));
    } catch {
      return undefined;
    }
  }
}

/** Drop exact duplicates (same id raised at the same moment) and keep the order. */
export function uniqueAlerts(list: readonly AlertObject[]): AlertObject[] {
  const seen = new Set<string>();
  const out: AlertObject[] = [];
  for (const alert of list) {
    if (!alert || typeof alert.id !== 'string') continue;
    const key = alertIdentity(alert);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(alert);
  }
  return out;
}

/**
 * One alert's identity. The backend used to build the id from the trade
 * timestamp, so two alerts raised minutes apart on the same stale print shared
 * an id (41 React duplicate-key errors per walk, QA V16); the creation time
 * tells them apart.
 */
export function alertIdentity(alert: Pick<AlertObject, 'id' | 'created_ts'>): string {
  return `${alert.id}@${typeof alert.created_ts === 'number' ? alert.created_ts : ''}`;
}
