/**
 * One dismissed list for the setup proposals (ADR 042 draft, spec K): the alert card that floats on every tab
 * and the Bots page's inbox read and write the same ids, so a proposal dismissed in one is gone from both.
 * Kept for the browser session (`sessionStorage` `nova.setups.dismissed` = `{schema_version: 1, ids: string[]}`,
 * newest last, at most `PROPOSAL_DISMISSED_MAX`); an unknown version is ignored, never guessed. Storage that
 * throws (a private window) keeps the list in memory for the page's life and says so in the console.
 */
import { PROPOSAL_DISMISSED_KEY, PROPOSAL_DISMISSED_MAX } from '../constantGroups/setups';

const SCHEMA_VERSION = 1;

let ids: ReadonlySet<string> | null = null;
const listeners = new Set<() => void>();

function session(): Storage | null {
  try {
    return typeof sessionStorage === 'undefined' ? null : sessionStorage;
  } catch (e) {
    console.warn('[Nova] dismissed proposals: sessionStorage is not available; kept in memory', e);
    return null;
  }
}

/** The stored ids; empty when nothing is stored, the value is unreadable or its version unknown. */
export function parseDismissed(raw: string | null): string[] {
  if (!raw) return [];
  try {
    const v: unknown = JSON.parse(raw);
    if (!v || typeof v !== 'object' || Array.isArray(v)) return [];
    const row = v as { schema_version?: unknown; ids?: unknown };
    if (row.schema_version !== SCHEMA_VERSION || !Array.isArray(row.ids)) return [];
    return row.ids.filter((x): x is string => typeof x === 'string');
  } catch (e) {
    console.warn('[Nova] dismissed proposals: the stored list is not JSON; starting empty', e);
    return [];
  }
}

function load(): ReadonlySet<string> {
  if (ids) return ids;
  let raw: string | null = null;
  try {
    raw = session()?.getItem(PROPOSAL_DISMISSED_KEY) ?? null;
  } catch (e) {
    console.warn('[Nova] dismissed proposals could not be read; starting empty', e);
  }
  ids = new Set(parseDismissed(raw));
  return ids;
}

function save(next: ReadonlySet<string>): void {
  try {
    session()?.setItem(PROPOSAL_DISMISSED_KEY, JSON.stringify({
      schema_version: SCHEMA_VERSION,
      ids: [...next].slice(-PROPOSAL_DISMISSED_MAX),
    }));
  } catch (e) {
    console.warn('[Nova] dismissed proposals could not be saved; they last until the page reloads', e);
  }
}

/** The dismissed ids now: one object per change, so a reader redraws only when the list moves. */
export function dismissedProposals(): ReadonlySet<string> {
  return load();
}

export function isDismissed(id: string): boolean {
  return load().has(id);
}

/** Dismiss one proposal or several (a symbol's card dismisses every setup that raised one). */
export function dismiss(id: string | readonly string[]): void {
  const add = typeof id === 'string' ? [id] : id;
  const now = load();
  if (add.every(x => now.has(x))) return;
  const next = new Set(now);
  for (const x of add) next.add(x);
  ids = next;
  save(next);
  for (const fn of [...listeners]) fn();
}

/** Called on every change, in this window. */
export function subscribe(fn: () => void): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

export function _resetDismissedForTests(): void {
  ids = null;
  listeners.clear();
}
