/**
 * Persisted rail chrome: collapsed-to-icons.
 *
 * Owner: this module (read + write). Invalidation: schema bump -- a payload
 * with an unknown `schema_version` is ignored and reported, never guessed at
 * (persisted-state.mdc). `collapsed` is tri-state: `null` means the operator
 * has not chosen, so the rail follows the view (icons on the Desk, labels
 * elsewhere -- see workspace/navRailStore.navRailCollapsedDefault).
 *
 * The Scanner tree no longer folds (operator ask, 2026-09-23): a stored
 * `scannerFolded` from an earlier build is read past and dropped on the next
 * write -- dropping an ignored field needs no schema bump.
 *
 * v1 -> v2 is a known rule, not a guess: v1 had no "not chosen" collapse state
 * and wrote `collapsed: false` on every fold write, so v1 `true` is a choice and
 * v1 `false` is not.
 */
import {
  NAV_RAIL_SCHEMA_VERSION,
  NAV_RAIL_SCHEMA_VERSION_LEGACY,
  NAV_RAIL_STORAGE_KEY,
} from '../constantGroups/nav_rail';

export type NavRailPrefs = {
  collapsed: boolean | null;
};

export const NAV_RAIL_DEFAULT_PREFS: NavRailPrefs = {
  collapsed: null,
};

type Stored = NavRailPrefs & { schema_version: number };

function storage(): Storage | null {
  try {
    return typeof window === 'undefined' ? null : window.localStorage;
  } catch {
    return null;
  }
}

function boolOrNull(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null;
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
    if (parsed.schema_version === NAV_RAIL_SCHEMA_VERSION_LEGACY) {
      return { collapsed: parsed.collapsed === true ? true : null };
    }
    if (parsed.schema_version !== NAV_RAIL_SCHEMA_VERSION) {
      console.warn(
        `[Nova] ${NAV_RAIL_STORAGE_KEY}: unknown schema_version ${String(parsed.schema_version)} -- using defaults`,
      );
      return NAV_RAIL_DEFAULT_PREFS;
    }
    return { collapsed: boolOrNull(parsed.collapsed) };
  } catch (err) {
    console.warn(`[Nova] ${NAV_RAIL_STORAGE_KEY}: unreadable -- using defaults`, err);
    return NAV_RAIL_DEFAULT_PREFS;
  }
}

export function writeNavRailPrefs(prefs: NavRailPrefs): void {
  const store = storage();
  if (!store) return;
  const payload: Stored = { schema_version: NAV_RAIL_SCHEMA_VERSION, collapsed: prefs.collapsed };
  try {
    store.setItem(NAV_RAIL_STORAGE_KEY, JSON.stringify(payload));
  } catch (err) {
    console.warn(`[Nova] ${NAV_RAIL_STORAGE_KEY}: write failed`, err);
  }
}
