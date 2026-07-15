/**
 * Shared exchange filter — persisted to localStorage.
 * filterRows() drops any row whose exchange is not in the active set.
 * Rows with a null/empty exchange are treated as non-matching.
 */
import { useCallback, useState } from 'react';
import {
  SCANNER_EXCHANGE_DEFAULTS,
  SCANNER_EXCHANGE_OPTIONS,
  SCANNER_EXCHANGE_STORAGE_KEY,
} from '../constants';

function loadFromStorage(): string[] {
  try {
    const raw = localStorage.getItem(SCANNER_EXCHANGE_STORAGE_KEY);
    if (!raw) return SCANNER_EXCHANGE_DEFAULTS;
    const parsed = JSON.parse(raw) as unknown;
    if (Array.isArray(parsed) && parsed.every(x => typeof x === 'string')) {
      // Only keep values that are still valid options
      const kept = parsed.filter(x =>
        (SCANNER_EXCHANGE_OPTIONS as readonly string[]).includes(x),
      );
      return kept.length > 0 ? kept : SCANNER_EXCHANGE_DEFAULTS;
    }
  } catch {
    // ignore
  }
  return SCANNER_EXCHANGE_DEFAULTS;
}

function saveToStorage(selected: string[]) {
  try {
    localStorage.setItem(SCANNER_EXCHANGE_STORAGE_KEY, JSON.stringify(selected));
  } catch {
    // ignore
  }
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
    <T extends { exchange?: string | null }>(rows: T[]): T[] => {
      // When all options are checked, skip filtering (show everything)
      if (selected.length === SCANNER_EXCHANGE_OPTIONS.length) return rows;
      return rows.filter(r => r.exchange && selected.includes(r.exchange));
    },
    [selected],
  );

  return { selected, toggle, selectAll, filterRows };
}
