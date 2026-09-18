import { describe, expect, it } from 'vitest';
import { ORDER_TABLE_COLUMNS_STORAGE_KEY } from '../constantGroups/chart_api';
import { SCANNER_ACTIVE_TAB_STORAGE_KEY } from '../constantGroups/market_ui';
import { HOD_MOMO_ALERT_SOUND_KEY } from '../hod_momo/hodMomoAlertSound';
import {
  exportPrefsBundle,
  importPrefsBundle,
  PREFS_BUNDLE_KEYS,
  PREFS_BUNDLE_VERSION,
} from './prefsBundle';

function memoryStorage(initial: Record<string, string> = {}) {
  const data = { ...initial };
  return {
    getItem: (key: string) => (key in data ? data[key] : null),
    setItem: (key: string, value: string) => {
      data[key] = value;
    },
    data,
  };
}

describe('prefsBundle', () => {
  it('exports known keys only', () => {
    const storage = memoryStorage({
      'nova.theme': 'dark',
      'unrelated': 'nope',
    });
    const bundle = exportPrefsBundle(storage);
    expect(bundle.version).toBe(PREFS_BUNDLE_VERSION);
    expect(bundle.prefs).toEqual({ 'nova.theme': 'dark' });
    expect(bundle.prefs.unrelated).toBeUndefined();
  });

  it('imports only allowlisted keys', () => {
    const storage = memoryStorage();
    const written = importPrefsBundle(
      {
        version: PREFS_BUNDLE_VERSION,
        exported_at: '2026-08-17T00:00:00.000Z',
        prefs: {
          'nova.theme': 'light',
          'evil.key': 'x',
        },
      },
      storage,
    );
    expect(written).toBe(1);
    expect(storage.data['nova.theme']).toBe('light');
    expect(storage.data['evil.key']).toBeUndefined();
  });

  it('allowlists the current order-table column-store key', () => {
    expect(PREFS_BUNDLE_KEYS).toContain(ORDER_TABLE_COLUMNS_STORAGE_KEY);
    expect(ORDER_TABLE_COLUMNS_STORAGE_KEY).toBe(
      'nova.ibkr.orderTable.columns.v7',
    );
  });

  it('allowlists the HOD Momo banner sound key', () => {
    expect(PREFS_BUNDLE_KEYS).toContain(HOD_MOMO_ALERT_SOUND_KEY);
  });

  it('allowlists the scanner activeTab persist key', () => {
    expect(PREFS_BUNDLE_KEYS).toContain(SCANNER_ACTIVE_TAB_STORAGE_KEY);
    const storage = memoryStorage({
      [SCANNER_ACTIVE_TAB_STORAGE_KEY]: '{"schema_version":1,"value":"gainers"}',
    });
    const bundle = exportPrefsBundle(storage);
    expect(bundle.prefs[SCANNER_ACTIVE_TAB_STORAGE_KEY]).toContain('gainers');
  });
});
