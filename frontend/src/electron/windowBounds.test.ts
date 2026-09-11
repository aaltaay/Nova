import { describe, expect, it } from 'vitest';
import {
  WINDOW_BOUNDS_SCHEMA_VERSION,
  boundsVisibleOnDisplays,
  emptyBoundsStore,
  parseBoundsStore,
  pickStoredBounds,
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
});
