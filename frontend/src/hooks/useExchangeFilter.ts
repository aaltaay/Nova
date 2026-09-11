/**
 * Shared exchange filter — persisted to localStorage.
 * filterRows() drops a row only when its exchange is KNOWN and unselected.
 * A row with a null/empty/unrecognized exchange fails open (kept) — IBKR
 * discovery rows do not carry a listing exchange the moment they are
 * admitted, and hiding them silently blanked the desk (2026-08-25).
 */
import { useCallback, useState } from 'react';
import {
  SCANNER_EXCHANGE_DEFAULTS,
  SCANNER_EXCHANGE_OPTIONS,
  SCANNER_EXCHANGE_STORAGE_KEY,
} from '../constants';
import { readPref, writePref } from '../utils/prefStore';

/** Pure predicate — exported so tests exercise the real filter, not a copy. */
export function filterRowsBySelection<T extends { exchange?: string | null }>(
  selected: string[],
  rows: T[],
): T[] {
  // When all options are checked, skip filtering (show everything).
  if (selected.length === SCANNER_EXCHANGE_OPTIONS.length) return rows;
  return rows.filter(r => !r.exchange || selected.includes(r.exchange));
}

function parseExchangeList(raw: unknown): string[] | null {
  if (!Array.isArray(raw) || !raw.every((x) => typeof x === 'string')) return null;
  const kept = raw.filter((x) =>
    (SCANNER_EXCHANGE_OPTIONS as readonly string[]).includes(x),
  );
  return kept.length > 0 ? kept : null;
}

function loadFromStorage(): string[] {
  return readPref(
    SCANNER_EXCHANGE_STORAGE_KEY,
    SCANNER_EXCHANGE_DEFAULTS,
    parseExchangeList,
  );
}

function saveToStorage(selected: string[]) {
  writePref(SCANNER_EXCHANGE_STORAGE_KEY, selected);
}

export interface ExchangeFilter {
  selected: string[];
  toggle: (exchange: string) => void;
  selectAll: () => void;
  filterRows: <T extends { exchange?: string | null }>(rows: T[]) => T[];
}

export function useExchangeFilter(): ExchangeFilter {
  const [selected, setSelected] = useState<string[]>(loadFromStorage);

  const toggle = useCallback((exchange: string) => {
    setSelected(prev => {
      const next = prev.includes(exchange)
        ? prev.filter(e => e !== exchange)
        : [...prev, exchange];
      // Always keep at least one exchange selected
      const result = next.length > 0 ? next : prev;
      saveToStorage(result);
      return result;
    });
  }, []);

  const selectAll = useCallback(() => {
    const all = [...SCANNER_EXCHANGE_OPTIONS];
    setSelected(all);
    saveToStorage(all);
  }, []);

  const filterRows = useCallback(
    <T extends { exchange?: string | null }>(rows: T[]): T[] =>
      filterRowsBySelection(selected, rows),
    [selected],
  );

  return { selected, toggle, selectAll, filterRows };
}
