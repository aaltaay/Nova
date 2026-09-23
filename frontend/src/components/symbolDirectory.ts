/**
 * The listed-symbol directory the bar search reads: every active US equity
 * listing with its company name and exchange (`GET /api/symbols/directory`,
 * AGENTS.md section 3). Loaded once, on the search's first focus, and shared
 * by every mounted search; refreshed after SYMBOL_DIRECTORY_REFRESH_MS.
 *
 * A failed load leaves the search on desk symbols and says so -- it never
 * invents a listing.
 */
import { useEffect, useSyncExternalStore } from 'react';
import { API_BASE_URL } from '../constantGroups/chart_api';
import {
  SYMBOL_DIRECTORY_PATH,
  SYMBOL_DIRECTORY_REFRESH_MS,
  SYMBOL_DIRECTORY_RETRY_MS,
} from '../constantGroups/global_bar';

export interface DirectoryEntry {
  symbol: string;
  name: string;
  /** Upper-cased once, for matching. */
  nameUpper: string;
  exchange: string;
}

export interface SymbolDirectory {
  entries: readonly DirectoryEntry[];
  bySymbol: ReadonlyMap<string, DirectoryEntry>;
}

export type SymbolDirectoryStatus = 'idle' | 'loading' | 'ready' | 'error';

export interface SymbolDirectoryState {
  status: SymbolDirectoryStatus;
  directory: SymbolDirectory | null;
  error: string | null;
}

/** Pure: wire rows `[symbol, name, exchange]` -> the searchable directory. */
export function buildSymbolDirectory(rows: unknown): SymbolDirectory {
  const entries: DirectoryEntry[] = [];
  const bySymbol = new Map<string, DirectoryEntry>();
  if (Array.isArray(rows)) {
    for (const row of rows) {
      if (!Array.isArray(row) || typeof row[0] !== 'string' || !row[0]) continue;
      const symbol = row[0].toUpperCase();
      if (bySymbol.has(symbol)) continue;
      const name = typeof row[1] === 'string' ? row[1] : '';
      const exchange = typeof row[2] === 'string' ? row[2] : '';
      const entry = { symbol, name, nameUpper: name.toUpperCase(), exchange };
      entries.push(entry);
      bySymbol.set(symbol, entry);
    }
  }
  return { entries, bySymbol };
}

let state: SymbolDirectoryState = { status: 'idle', directory: null, error: null };
let loadedAt = 0;
let failedAt = 0;
let inflight: Promise<void> | null = null;
const listeners = new Set<() => void>();

function publish(next: SymbolDirectoryState) {
  state = next;
  listeners.forEach((fn) => fn());
}

function subscribe(fn: () => void) {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

function getState() {
  return state;
}

/** Load (or refresh) the directory unless it is fresh, loading, or backing off. */
export function ensureSymbolDirectory(now = Date.now()): Promise<void> {
  if (inflight) return inflight;
  if (state.directory && now - loadedAt < SYMBOL_DIRECTORY_REFRESH_MS) return Promise.resolve();
  if (state.status === 'error' && now - failedAt < SYMBOL_DIRECTORY_RETRY_MS) return Promise.resolve();
  publish({ ...state, status: state.directory ? 'ready' : 'loading' });
  inflight = (async () => {
    try {
      const resp = await fetch(`${API_BASE_URL}${SYMBOL_DIRECTORY_PATH}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const body = (await resp.json()) as { symbols?: unknown; error?: unknown };
      const directory = buildSymbolDirectory(body.symbols);
      const error = typeof body.error === 'string' ? body.error : null;
      if (directory.entries.length) {
        loadedAt = Date.now();
        publish({ status: 'ready', directory, error: null });
      } else {
        failedAt = Date.now();
        publish({ status: state.directory ? 'ready' : 'error', directory: state.directory, error: error ?? 'empty directory' });
      }
    } catch (err) {
      failedAt = Date.now();
      const message = err instanceof Error ? err.message : String(err);
      publish({ status: state.directory ? 'ready' : 'error', directory: state.directory, error: message });
    } finally {
      inflight = null;
    }
  })();
  return inflight;
}

/** The shared directory; `wanted` starts (or refreshes) the load. */
export function useSymbolDirectory(wanted: boolean): SymbolDirectoryState {
  const snapshot = useSyncExternalStore(subscribe, getState, getState);
  useEffect(() => {
    if (wanted) void ensureSymbolDirectory();
  }, [wanted]);
  return snapshot;
}

export function resetSymbolDirectoryForTests(next?: SymbolDirectoryState) {
  state = next ?? { status: 'idle', directory: null, error: null };
  loadedAt = next?.directory ? Date.now() : 0;
  failedAt = 0;
  inflight = null;
  listeners.forEach((fn) => fn());
}
