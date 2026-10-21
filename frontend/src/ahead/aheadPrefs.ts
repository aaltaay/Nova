/**
 * Ahead's switch, scope and "Show before it has earned it" (ADR 065): one choice per viewer for every Trader tab and
 * window, kept between restarts in `nova.ahead.prefs` (a versioned envelope), off / All / off until the operator
 * changes it. Another window's change arrives through the `storage` event. While `shown` is off the desk asks nothing.
 */
import { useSyncExternalStore } from 'react';
import { readPref, writePref } from '../utils/prefStore';
import { AHEAD_PREFS_KEY, AHEAD_SCOPES } from './aheadConstants';
import type { AheadPrefs, AheadScope } from './aheadTypes';

export const AHEAD_DEFAULT_PREFS: AheadPrefs = { shown: false, scope: 'all', unearned: false };

/** Each field on its own: a bad one falls back to its default, the rest are kept. */
export function parseAheadPrefs(raw: unknown): AheadPrefs | null {
  if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) return null;
  const r = raw as Record<string, unknown>;
  return {
    shown: typeof r.shown === 'boolean' ? r.shown : AHEAD_DEFAULT_PREFS.shown,
    scope: AHEAD_SCOPES.includes(r.scope as AheadScope) ? (r.scope as AheadScope) : AHEAD_DEFAULT_PREFS.scope,
    unearned: typeof r.unearned === 'boolean' ? r.unearned : AHEAD_DEFAULT_PREFS.unearned,
  };
}

function load(): AheadPrefs {
  if (typeof localStorage === 'undefined') return AHEAD_DEFAULT_PREFS;
  return readPref(AHEAD_PREFS_KEY, AHEAD_DEFAULT_PREFS, parseAheadPrefs);
}

let prefs: AheadPrefs = load();
const listeners = new Set<() => void>();

function emit(): void {
  for (const l of listeners) l();
}

if (typeof window !== 'undefined') {
  window.addEventListener('storage', (e) => {
    if (e.key !== AHEAD_PREFS_KEY) return;
    prefs = load();
    emit();
  });
}

export function readAheadPrefs(): AheadPrefs {
  return prefs;
}

export function setAheadPrefs(patch: Partial<AheadPrefs>): void {
  const next = parseAheadPrefs({ ...prefs, ...patch }) ?? AHEAD_DEFAULT_PREFS;
  if (next.shown === prefs.shown && next.scope === prefs.scope && next.unearned === prefs.unearned) return;
  prefs = next;
  // writePref keeps the choice for this session when storage refuses it (the sample desk, a private window).
  if (typeof localStorage !== 'undefined') writePref(AHEAD_PREFS_KEY, prefs);
  emit();
}

function subscribe(l: () => void): () => void {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
}

export function useAheadPrefs(): AheadPrefs {
  return useSyncExternalStore(subscribe, readAheadPrefs, readAheadPrefs);
}

/** Tests only: read storage again as a fresh window would. */
export function reloadAheadPrefsForTesting(): void {
  prefs = load();
  emit();
}
