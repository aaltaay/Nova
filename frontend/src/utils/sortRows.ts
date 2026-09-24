import { SCANNER_TIME_SORT_KEYS } from '../constants';
import { firstSortDir } from '../table_sort';
import type { SortConfig } from '../types/scanner';

/** Cycle a scanner column like every other table (`table_sort/`): the first
 * click sorts text A to Z and numbers highest first -- read from `rows` --
 * (a time column newest first), the second flips it, the third returns to
 * the list's own order. */
export function toggleSort<T>(
  current: SortConfig,
  setter: (s: SortConfig) => void,
  key: string,
  rows: readonly T[],
): void {
  const first = SCANNER_TIME_SORT_KEYS.has(key)
    ? 'desc'
    : firstSortDir<T>(row => (row as Record<string, unknown>)[key] as string | number | null, rows);
  if (current.key !== key || !current.dir) setter({ key, dir: first });
  else if (current.dir === first) setter({ key, dir: first === 'asc' ? 'desc' : 'asc' });
  else setter({ key: '', dir: null });
}

/** Stable sort of rows by SortConfig (nulls last). */
export function sortedArray<T>(arr: T[], cfg: SortConfig): T[] {
  if (!cfg.key || !cfg.dir) return arr;
  const { key, dir } = cfg;
  return [...arr].sort((a, b) => {
    const av = (a as Record<string, unknown>)[key] ?? null;
    const bv = (b as Record<string, unknown>)[key] ?? null;
    if (av === null && bv === null) return 0;
    if (av === null) return 1;
    if (bv === null) return -1;
    let cmp = 0;
    if (typeof av === 'number' && typeof bv === 'number') {
      cmp = av - bv;
    } else {
      cmp = String(av).localeCompare(String(bv));
    }
    return dir === 'asc' ? cmp : -cmp;
  });
}
