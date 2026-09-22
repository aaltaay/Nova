/**
 * Persisted rail chrome: collapsed-to-icons and the operator's Scanner fold.
 *
 * Owner: this module (read + write). Invalidation: schema bump -- a payload
 * with an unknown `schema_version` is ignored and reported, never guessed at
 * (persisted-state.mdc). `scannerFolded: null` means the operator has not
 * chosen, so the rail follows the view (open on Scanner, folded elsewhere).
 */
import {
  NAV_RAIL_SCHEMA_VERSION,
  NAV_RAIL_STORAGE_KEY,
} from '../constantGroups/nav_rail';

export type NavRailPrefs = {
  collapsed: boolean;
  scannerFolded: boolean | null;
};

export const NAV_RAIL_DEFAULT_PREFS: NavRailPrefs = {
  collapsed: false,
  scannerFolded: null,
};

type Stored = NavRailPrefs & { schema_version: number };

function storage(): Storage | null {
  try {
    return typeof window === 'undefined' ? null : window.localStorage;
  } catch {
    return null;
  }
}

export function readNavRailPrefs(): NavRailPrefs {
  const store = storage();
  if (!store) return NAV_RAIL_DEFAULT_PREFS;
  let raw: string | null = null;
  try {
    raw = store.getItem(NAV_RAIL_STORAGE_KEY);
  } catch {
    return NAV_RAIL_DEFAULT_PREFS;
  }
  if (!raw) return NAV_RAIL_DEFAULT_PREFS;
  try {
    const parsed = JSON.parse(raw) as Partial<Stored> | null;
    if (!parsed || typeof parsed !== 'object') return NAV_RAIL_DEFAULT_PREFS;
    if (parsed.schema_version !== NAV_RAIL_SCHEMA_VERSION) {
      console.warn(
        `[Nova] ${NAV_RAIL_STORAGE_KEY}: unknown schema_version ${String(parsed.schema_version)} -- using defaults`,
      );
      return NAV_RAIL_DEFAULT_PREFS;
    }
    return {
      collapsed: parsed.collapsed === true,
      scannerFolded: typeof parsed.scannerFolded === 'boolean' ? parsed.scannerFolded : null,
    };
  } catch (err) {
    console.warn(`[Nova] ${NAV_RAIL_STORAGE_KEY}: unreadable -- using defaults`, err);
    return NAV_RAIL_DEFAULT_PREFS;
  }
}

export function writeNavRailPrefs(prefs: NavRailPrefs): void {
  const store = storage();
  if (!store) return;
  const payload: Stored = { schema_version: NAV_RAIL_SCHEMA_VERSION, ...prefs };
  try {
    store.setItem(NAV_RAIL_STORAGE_KEY, JSON.stringify(payload));
  } catch (err) {
    console.warn(`[Nova] ${NAV_RAIL_STORAGE_KEY}: write failed`, err);
  }
}
