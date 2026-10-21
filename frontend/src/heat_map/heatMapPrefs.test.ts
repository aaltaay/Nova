/** @vitest-environment jsdom */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { HEAT_PREFS_KEY } from './heatMapConstants';
import { HEAT_PREFS_DEFAULT, parseHeatPrefs } from './heatMapPrefs';

describe('the heat map choices (ADR 061)', () => {
  afterEach(() => {
    localStorage.clear();
    vi.resetModules();
  });

  it('starts off, at 5 minutes, 1k-share dots, and keeps what the operator picks', async () => {
    const prefs = await import('./heatMapPrefs');
    expect(prefs.heatPrefs()).toEqual(HEAT_PREFS_DEFAULT);
    prefs.setHeatPrefs({ shown: true, windowSec: 900, minDot: 2000, brightness: 70 });
    expect(JSON.parse(localStorage.getItem(HEAT_PREFS_KEY)!)).toEqual({
      schema_version: 1, shown: true, windowSec: 900, minDot: 2000, brightness: 70,
    });
    vi.resetModules();
    expect((await import('./heatMapPrefs')).heatPrefs().windowSec).toBe(900);
  });

  it("follows another window's change", async () => {
    const prefs = await import('./heatMapPrefs');
    localStorage.setItem(HEAT_PREFS_KEY, JSON.stringify({ schema_version: 1, shown: true }));
    window.dispatchEvent(new StorageEvent('storage', { key: HEAT_PREFS_KEY }));
    expect(prefs.heatPrefs().shown).toBe(true);
  });

  it('reads anything malformed, out of range or of another version as the defaults', () => {
    expect(parseHeatPrefs('not json')).toEqual(HEAT_PREFS_DEFAULT);
    expect(parseHeatPrefs(JSON.stringify({ schema_version: 2, shown: true }))).toEqual(HEAT_PREFS_DEFAULT);
    const p = parseHeatPrefs(JSON.stringify({ schema_version: 1, windowSec: 99999, minDot: 777, brightness: -5 }));
    expect(p.windowSec).toBe(1800);
    expect(p.minDot).toBe(1000);
    expect(p.brightness).toBe(0);
  });
});
