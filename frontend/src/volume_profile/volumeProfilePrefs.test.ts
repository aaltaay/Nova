/** @vitest-environment jsdom */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { VP_PREFS_KEY } from './volumeProfileConstants';

describe('the Profile switch', () => {
  afterEach(() => {
    localStorage.clear();
    vi.resetModules();
  });

  it('is off until the operator turns it on, and keeps the choice', async () => {
    const prefs = await import('./volumeProfilePrefs');
    expect(prefs.profileShown()).toBe(false);
    prefs.setProfileShown(true);
    expect(prefs.profileShown()).toBe(true);
    expect(localStorage.getItem(VP_PREFS_KEY)).toBe('1');
    vi.resetModules();
    expect((await import('./volumeProfilePrefs')).profileShown()).toBe(true);
  });

  it("follows another window's change", async () => {
    const prefs = await import('./volumeProfilePrefs');
    localStorage.setItem(VP_PREFS_KEY, '1');
    window.dispatchEvent(new StorageEvent('storage', { key: VP_PREFS_KEY }));
    expect(prefs.profileShown()).toBe(true);
    localStorage.setItem(VP_PREFS_KEY, '0');
    window.dispatchEvent(new StorageEvent('storage', { key: VP_PREFS_KEY }));
    expect(prefs.profileShown()).toBe(false);
  });
});
