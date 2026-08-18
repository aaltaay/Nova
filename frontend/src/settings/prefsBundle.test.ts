import { describe, expect, it } from 'vitest';
import { exportPrefsBundle, importPrefsBundle, PREFS_BUNDLE_VERSION } from './prefsBundle';

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
});
