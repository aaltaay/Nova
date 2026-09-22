/**
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it } from 'vitest';
import { SCANNER_ACTIVE_TAB_STORAGE_KEY } from '../constants';
import { HOD_MOMO_STRIP_STORAGE_KEY } from '../hod_momo/hodMomoStripConstants';
import { PREFS_BUNDLE_KEYS } from '../settings/prefsBundle';
import { PREF_SCHEMA_VERSION } from '../utils/prefStore';
import { DEFAULT_ACTIVE_TAB } from './registry';
import {
  applySessionAutoSwitch,
  initialScannerTabState,
  parsePersistedScannerTab,
  readPersistedScannerTab,
  writePersistedScannerTab,
} from './scannerActiveTabPersist';

beforeEach(() => {
  localStorage.clear();
});

describe('scannerActiveTabPersist restore', () => {
  it('returns no pick when unset so session auto-switch can run', () => {
    expect(readPersistedScannerTab()).toBeNull();
    expect(initialScannerTabState()).toEqual({
      tab: DEFAULT_ACTIVE_TAB,
      userPicked: false,
    });
  });

  it('restores a user-picked scanner tab on mount', () => {
    writePersistedScannerTab('gainers');
    expect(readPersistedScannerTab()).toBe('gainers');
    expect(initialScannerTabState()).toEqual({
      tab: 'gainers',
      userPicked: true,
    });

    writePersistedScannerTab('large_cap');
    expect(initialScannerTabState()).toEqual({
      tab: 'large_cap',
      userPicked: true,
    });

    writePersistedScannerTab('catalysts');
    expect(initialScannerTabState()).toEqual({
      tab: 'catalysts',
      userPicked: true,
    });

    writePersistedScannerTab('volume_boost');
    expect(initialScannerTabState()).toEqual({
      tab: 'volume_boost',
      userPicked: true,
    });
  });

  it('writes a prefStore envelope under the named scanner key', () => {
    writePersistedScannerTab('gainers');
    const stored = JSON.parse(
      localStorage.getItem(SCANNER_ACTIVE_TAB_STORAGE_KEY) ?? '',
    );
    expect(stored.schema_version).toBe(PREF_SCHEMA_VERSION);
    expect(stored.value).toBe('gainers');
  });

  it('refuses dock, account, and junk values', () => {
    expect(parsePersistedScannerTab('hod_momo')).toBeNull();
    expect(parsePersistedScannerTab('running_up')).toBeNull();
    expect(parsePersistedScannerTab('trading')).toBeNull();
    expect(parsePersistedScannerTab('watchlist')).toBeNull();
    expect(parsePersistedScannerTab('nope')).toBeNull();
    expect(parsePersistedScannerTab(1)).toBeNull();

    writePersistedScannerTab('hod_momo');
    writePersistedScannerTab('trading');
    expect(localStorage.getItem(SCANNER_ACTIVE_TAB_STORAGE_KEY)).toBeNull();
    expect(readPersistedScannerTab()).toBeNull();
    expect(initialScannerTabState().userPicked).toBe(false);
  });

  it('does not touch the HOD strip key', () => {
    const strip = '{"schema_version":1,"rows":6,"folded":true}';
    localStorage.setItem(HOD_MOMO_STRIP_STORAGE_KEY, strip);
    writePersistedScannerTab('catalysts');
    expect(localStorage.getItem(HOD_MOMO_STRIP_STORAGE_KEY)).toBe(strip);
    expect(PREFS_BUNDLE_KEYS).toContain(HOD_MOMO_STRIP_STORAGE_KEY);
    expect(SCANNER_ACTIVE_TAB_STORAGE_KEY).not.toContain('hodMomo');
    expect(PREFS_BUNDLE_KEYS).toContain(SCANNER_ACTIVE_TAB_STORAGE_KEY);
  });
});

describe('scannerActiveTabPersist session auto-switch', () => {
  it('does not fight premkt/RTH/AH defaults until the user has picked', () => {
    expect(applySessionAutoSwitch('gappers', 'market', false)).toBe('gappers');
    expect(applySessionAutoSwitch('gappers', 'afterhours', false)).toBe('gappers');
    expect(applySessionAutoSwitch('gainers', 'premarket', false)).toBe('gainers');
    expect(applySessionAutoSwitch('strategy', 'market', false)).toBe('strategy');
    expect(applySessionAutoSwitch('large_cap', 'market', false)).toBe('gainers');
    expect(applySessionAutoSwitch('catalysts', 'afterhours', false)).toBe(
      'afterhours',
    );
    expect(applySessionAutoSwitch('catalysts', 'premarket', false)).toBe(
      'gappers',
    );
  });

  it('keeps a user pick (including a restored persist) across session modes', () => {
    expect(applySessionAutoSwitch('large_cap', 'market', true)).toBe('large_cap');
    expect(applySessionAutoSwitch('catalysts', 'afterhours', true)).toBe(
      'catalysts',
    );
    expect(applySessionAutoSwitch('volume_boost', 'market', true)).toBe(
      'volume_boost',
    );
    expect(applySessionAutoSwitch('gainers', 'premarket', true)).toBe('gainers');
    expect(applySessionAutoSwitch('afterhours', 'market', true)).toBe(
      'afterhours',
    );
  });

  it('treats a restored persist as a user pick so mount does not snap to session default', () => {
    writePersistedScannerTab('large_cap');
    const init = initialScannerTabState();
    expect(init.userPicked).toBe(true);
    expect(applySessionAutoSwitch(init.tab, 'market', init.userPicked)).toBe(
      'large_cap',
    );
    expect(applySessionAutoSwitch(init.tab, 'afterhours', init.userPicked)).toBe(
      'large_cap',
    );
  });

  it('lets session defaults run when nothing is stored', () => {
    const init = initialScannerTabState();
    expect(init.userPicked).toBe(false);
    expect(applySessionAutoSwitch(init.tab, 'market', init.userPicked)).toBe(
      DEFAULT_ACTIVE_TAB,
    );
  });
});
