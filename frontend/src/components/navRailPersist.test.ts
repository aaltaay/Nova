/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  NAV_RAIL_SCHEMA_VERSION,
  NAV_RAIL_SCHEMA_VERSION_LEGACY,
  NAV_RAIL_STORAGE_KEY,
} from '../constantGroups/nav_rail';
import { NAV_RAIL_DEFAULT_PREFS, readNavRailPrefs, writeNavRailPrefs } from './navRailPersist';

describe('navRailPersist', () => {
  beforeEach(() => {
    localStorage.clear();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('defaults to "not chosen" for both the collapse and the fold', () => {
    expect(readNavRailPrefs()).toEqual({ collapsed: null, scannerFolded: null });
    expect(NAV_RAIL_DEFAULT_PREFS).toEqual({ collapsed: null, scannerFolded: null });
  });

  it('round-trips tri-state choices under the current schema', () => {
    writeNavRailPrefs({ collapsed: false, scannerFolded: true });
    expect(JSON.parse(localStorage.getItem(NAV_RAIL_STORAGE_KEY)!)).toEqual({
      schema_version: NAV_RAIL_SCHEMA_VERSION, collapsed: false, scannerFolded: true,
    });
    expect(readNavRailPrefs()).toEqual({ collapsed: false, scannerFolded: true });
    writeNavRailPrefs({ collapsed: null, scannerFolded: null });
    expect(readNavRailPrefs()).toEqual({ collapsed: null, scannerFolded: null });
  });

  it('migrates v1 by its known rule: collapsed true was a choice, false was the default it always wrote', () => {
    localStorage.setItem(NAV_RAIL_STORAGE_KEY, JSON.stringify({ schema_version: NAV_RAIL_SCHEMA_VERSION_LEGACY, collapsed: false, scannerFolded: true }));
    expect(readNavRailPrefs()).toEqual({ collapsed: null, scannerFolded: true });
    localStorage.setItem(NAV_RAIL_STORAGE_KEY, JSON.stringify({ schema_version: NAV_RAIL_SCHEMA_VERSION_LEGACY, collapsed: true, scannerFolded: false }));
    expect(readNavRailPrefs()).toEqual({ collapsed: true, scannerFolded: false });
  });

  it('ignores an unknown schema_version loudly and an unreadable payload quietly', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    localStorage.setItem(NAV_RAIL_STORAGE_KEY, JSON.stringify({ schema_version: 99, collapsed: true }));
    expect(readNavRailPrefs()).toEqual(NAV_RAIL_DEFAULT_PREFS);
    expect(warn).toHaveBeenCalledTimes(1);
    localStorage.setItem(NAV_RAIL_STORAGE_KEY, '{nope');
    expect(readNavRailPrefs()).toEqual(NAV_RAIL_DEFAULT_PREFS);
    expect(warn).toHaveBeenCalledTimes(2);
  });
});
