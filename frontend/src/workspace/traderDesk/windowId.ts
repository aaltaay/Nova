import { TRADER_WINDOW_ID_KEY } from '../../constantGroups/trader_view';

function newId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `tw-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

/** Stable per OS window (sessionStorage). */
export function getTraderWindowId(
  storage: Pick<Storage, 'getItem' | 'setItem'> | null = typeof sessionStorage === 'undefined'
    ? null
    : sessionStorage,
): string {
  if (!storage) return newId();
  try {
    const existing = storage.getItem(TRADER_WINDOW_ID_KEY);
    if (existing) return existing;
    const id = newId();
    storage.setItem(TRADER_WINDOW_ID_KEY, id);
    return id;
  } catch {
    return newId();
  }
}
