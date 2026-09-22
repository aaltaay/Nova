/**
 * Persisted Account page range preference (owner of ACCOUNT_RANGE_STORAGE_KEY).
 * Versioned: an unknown schema_version or an unknown range is ignored, never
 * migrated by guesswork (persisted-state.mdc). Per-viewer convenience only.
 */
import {
  ACCOUNT_HISTORY_DEFAULT_RANGE,
  ACCOUNT_HISTORY_RANGES,
  ACCOUNT_RANGE_SCHEMA_VERSION,
  ACCOUNT_RANGE_STORAGE_KEY,
  type AccountRange,
} from '../constantGroups/account_page';

interface StoredRange {
  schema_version: number;
  range: string;
}

export function isAccountRange(value: unknown): value is AccountRange {
  return typeof value === 'string' && (ACCOUNT_HISTORY_RANGES as readonly string[]).includes(value);
}

export function readAccountRangePref(storage: Storage | null = safeStorage()): AccountRange {
  if (!storage) return ACCOUNT_HISTORY_DEFAULT_RANGE;
  try {
    const raw = storage.getItem(ACCOUNT_RANGE_STORAGE_KEY);
    if (!raw) return ACCOUNT_HISTORY_DEFAULT_RANGE;
    const parsed = JSON.parse(raw) as Partial<StoredRange> | null;
    if (!parsed || parsed.schema_version !== ACCOUNT_RANGE_SCHEMA_VERSION) {
      return ACCOUNT_HISTORY_DEFAULT_RANGE;
    }
    return isAccountRange(parsed.range) ? parsed.range : ACCOUNT_HISTORY_DEFAULT_RANGE;
  } catch {
    return ACCOUNT_HISTORY_DEFAULT_RANGE;
  }
}

export function writeAccountRangePref(range: AccountRange, storage: Storage | null = safeStorage()): void {
  if (!storage) return;
  try {
    const stored: StoredRange = { schema_version: ACCOUNT_RANGE_SCHEMA_VERSION, range };
    storage.setItem(ACCOUNT_RANGE_STORAGE_KEY, JSON.stringify(stored));
  } catch {
    // Storage may be blocked (private window, quota); the page still works.
  }
}

function safeStorage(): Storage | null {
  try {
    return typeof window === 'undefined' ? null : window.localStorage;
  } catch {
    return null;
  }
}
