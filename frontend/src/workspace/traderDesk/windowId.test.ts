/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it } from 'vitest';
import {
  TRADER_FLOAT_ID_READY_KEY,
  TRADER_WINDOW_ID_KEY,
} from '../../constantGroups/trader_view';
import { getTraderWindowId } from './windowId';

function memoryStore(init: Record<string, string> = {}) {
  const data = new Map<string, string>(Object.entries(init));
  return {
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => {
      data.set(k, v);
    },
    removeItem: (k: string) => {
      data.delete(k);
    },
    data,
  };
}

describe('getTraderWindowId', () => {
  afterEach(() => {
    sessionStorage.removeItem(TRADER_WINDOW_ID_KEY);
    sessionStorage.removeItem(TRADER_FLOAT_ID_READY_KEY);
  });

  it('reuses a host id already in storage', () => {
    const storage = memoryStore({ [TRADER_WINDOW_ID_KEY]: 'host-abc' });
    expect(getTraderWindowId(storage, 'host')).toBe('host-abc');
  });

  it('remints when a float inherits the host window id from window.open', () => {
    const storage = memoryStore({ [TRADER_WINDOW_ID_KEY]: 'host-abc' });
    const floatId = getTraderWindowId(storage, 'float');
    expect(floatId).not.toBe('host-abc');
    expect(storage.getItem(TRADER_FLOAT_ID_READY_KEY)).toBe('1');
    expect(getTraderWindowId(storage, 'float')).toBe(floatId);
  });
});
