import {
  TRADER_FLOAT_ID_READY_KEY,
  TRADER_WINDOW_ID_KEY,
} from '../../constantGroups/trader_view';
import type { TraderDeskRole } from './protocol';

function newId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `tw-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

type IdStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

function defaultStorage(): IdStorage | null {
  return typeof sessionStorage === 'undefined' ? null : sessionStorage;
}

/**
 * Stable per OS window (sessionStorage).
 * Floats must remint: window.open copies the host's sessionStorage, including
 * the host windowId, which makes dock-request / drop look like a self-message
 * and the tab vanishes (#199).
 */
export function getTraderWindowId(
  storage?: IdStorage | null,
  role?: TraderDeskRole,
): string {
  const store = storage ?? defaultStorage();
  if (!store) return newId();
  try {
    if (role === 'float' && store.getItem(TRADER_FLOAT_ID_READY_KEY) !== '1') {
      store.removeItem(TRADER_WINDOW_ID_KEY);
      store.setItem(TRADER_FLOAT_ID_READY_KEY, '1');
    }
    const existing = store.getItem(TRADER_WINDOW_ID_KEY);
    if (existing) return existing;
    const id = newId();
    store.setItem(TRADER_WINDOW_ID_KEY, id);
    return id;
  } catch {
    return newId();
  }
}
