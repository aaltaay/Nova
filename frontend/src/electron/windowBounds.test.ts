import { describe, expect, it } from 'vitest';
import {
  WINDOW_BOUNDS_SCHEMA_VERSION,
  applyStoredPlacement,
  boundsVisibleOnDisplays,
  emptyBoundsStore,
  parseBoundsStore,
  pickStoredBounds,
  pickStoredPlacement,
  settleRoundTrip,
  traderWindowId,
  upsertWindowBounds,
} from '../../electron/windowBounds.mjs';

const display = { x: 0, y: 0, width: 1920, height: 1080 };

describe('windowBounds persist helpers', () => {
  it('builds trader ids and refuses unknown schema versions', () => {
    expect(traderWindowId('aapl')).toBe('trader:AAPL');
    expect(parseBoundsStore({ schema_version: 99, windows: { main: { x: 1 } } })).toEqual(
      emptyBoundsStore(),
    );
  });

  it('restores on-screen bounds and drops off-screen ones', () => {
    const store = upsertWindowBounds(emptyBoundsStore(), 'main', {
      x: 80,
      y: 60,
      width: 1400,
      height: 900,
    });
    expect(store.schema_version).toBe(WINDOW_BOUNDS_SCHEMA_VERSION);
    expect(pickStoredBounds(store, 'main', [display])).toEqual({
      x: 80,
      y: 60,
      width: 1400,
      height: 900,
    });
    expect(
      boundsVisibleOnDisplays({ x: 8000, y: 8000, width: 800, height: 600 }, [display]),
    ).toBe(false);
    expect(pickStoredBounds(store, 'missing', [display])).toBeNull();
  });

  // The desk's own layout: a 150% 4K monitor left of a 100% primary, as
  // Electron reports it in DIP. A rect Electron had inflated 1.5x there and
  // then saved spanned every monitor on the next launch.
  const scaled = { x: -2560, y: -509, width: 2560, height: 1441 };
  const primary = { x: 0, y: 0, width: 2560, height: 1392 };

  it('clamps an inflated rect onto the one display it mostly sits on', () => {
    const store = upsertWindowBounds(emptyBoundsStore(), 'main', {
      x: -2568,
      y: -517,
      width: 3840,
      height: 2091,
    });
    expect(pickStoredBounds(store, 'main', [scaled, primary])).toEqual(scaled);
  });

  it('keeps the maximized flag beside the normal bounds, reading old entries as not maximized', () => {
    const normal = { x: -2400, y: -401, width: 1600, height: 1000 };
    const store = upsertWindowBounds(emptyBoundsStore(), 'main', normal, true);
    expect(pickStoredPlacement(store, 'main', [scaled, primary])).toEqual({
      bounds: normal,
      maximized: true,
    });
    const legacy = parseBoundsStore({ schema_version: 1, windows: { main: normal } });
    expect(pickStoredPlacement(legacy, 'main', [scaled, primary])?.maximized).toBe(false);
  });

  it('re-applies the bounds after construction and maximizes on first show', () => {
    const calls: string[] = [];
    let onShow: (() => void) | null = null;
    const win = {
      setBounds: (b: unknown) => calls.push(`setBounds ${JSON.stringify(b)}`),
      maximize: () => calls.push('maximize'),
      isDestroyed: () => false,
      once: (event: string, fn: () => void) => {
        if (event === 'show') onShow = fn;
      },
    };
    const bounds = { x: 10, y: 20, width: 1200, height: 800 };
    applyStoredPlacement(win, { bounds, maximized: true });
    expect(calls).toEqual([`setBounds ${JSON.stringify(bounds)}`]);
    onShow!();
    expect(calls).toEqual([`setBounds ${JSON.stringify(bounds)}`, 'maximize']);
    applyStoredPlacement(win, null);
    expect(calls).toHaveLength(2);
  });

  it('saves the restored rect when the window reads it back a pixel off', () => {
    const applied = { x: -2400, y: -401, width: 1600, height: 1000 };
    expect(settleRoundTrip(applied, { ...applied, height: 1001 })).toBe(applied);
    const resized = { ...applied, width: 1700 };
    expect(settleRoundTrip(applied, resized)).toBe(resized);
    expect(settleRoundTrip(undefined, resized)).toBe(resized);
  });
});
