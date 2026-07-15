import type { SortConfig } from '../types/scanner';

/** Cycle sort: none → asc → desc → none for a column key. */
export function toggleSort(
  current: SortConfig,
  setter: (s: SortConfig) => void,
  key: string,
): void {
  if (current.key !== key) setter({ key, dir: 'asc' });
  else if (current.dir === 'asc') setter({ key, dir: 'desc' });
  else if (current.dir === 'desc') setter({ key: '', dir: null });
  else setter({ key, dir: 'asc' });
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
