/**
 * Focus rail sorting: the operator reorders the mirrored list by a column
 * header -- symbol, last, % or news -- like any table. No sort is the list's
 * own order (the scanner's rank, or newest raised first on the HOD lists).
 * A missing value always sorts last in either direction; it is never read
 * as zero.
 */
import { NEWS_FLAME_HOT_HOURS, NEWS_FLAME_MAX_HOURS, NEWS_FLAME_WARM_HOURS } from '../constants';
import { newsMark } from '../utils/catalystVerdict';
import type { FocusRow } from './focusRailState';

export const FOCUS_SORT_KEYS = ['symbol', 'price', 'gap', 'news'] as const;
export type FocusSortKey = (typeof FOCUS_SORT_KEYS)[number];
export type FocusSortDir = 'asc' | 'desc';

export interface FocusSort {
  key: FocusSortKey;
  dir: FocusSortDir;
}

/** The first click's direction: A-Z for symbols, biggest first for numbers,
 * news first for the news column. */
const FIRST_DIR: Record<FocusSortKey, FocusSortDir> = { symbol: 'asc', price: 'desc', gap: 'desc', news: 'desc' };

export function isFocusSortKey(value: unknown): value is FocusSortKey {
  return typeof value === 'string' && (FOCUS_SORT_KEYS as readonly string[]).includes(value);
}

/** A persisted sort, or null when it is missing or malformed. */
export function parseFocusSort(value: unknown): FocusSort | null {
  if (!value || typeof value !== 'object') return null;
  const { key, dir } = value as Partial<FocusSort>;
  if (!isFocusSortKey(key) || (dir !== 'asc' && dir !== 'desc')) return null;
  return { key, dir };
}

/** One header click: a new column starts at its first direction, the same
 * column flips once, and a third click returns to the list's own order. */
export function nextFocusSort(current: FocusSort | null, key: FocusSortKey): FocusSort | null {
  const first = FIRST_DIR[key];
  if (!current || current.key !== key) return { key, dir: first };
  if (current.dir === first) return { key, dir: first === 'asc' ? 'desc' : 'asc' };
  return null;
}

const AGE_RANK: Record<string, number> = { 'flame-hot': 3, 'flame-warm': 2, 'flame-cool': 1 };

function headlineAgeRank(headlineAt: string | null, nowMs: number): number {
  if (!headlineAt) return 0;
  const hours = (nowMs - new Date(headlineAt).getTime()) / 3_600_000;
  if (!Number.isFinite(hours) || hours > NEWS_FLAME_MAX_HOURS) return 0;
  if (hours <= NEWS_FLAME_HOT_HOURS) return 3;
  return hours <= NEWS_FLAME_WARM_HOURS ? 2 : 1;
}

/**
 * News rank, the order the news circle reads in (higher first): a catalyst
 * flame (red, orange, yellow), an unplaced headline ring, halted for news,
 * bad news, routine items, then nothing found. Unknown news -- a symbol no
 * scanner list carries, or a verdict not read yet -- is null and sorts last.
 */
export function focusNewsRank(row: FocusRow, nowMs: number): number | null {
  if (!row.newsKnown) return null;
  if (row.verdict === undefined) {
    const age = headlineAgeRank(row.headlineAt, nowMs);
    return age ? 30 + age : 0;
  }
  if (row.verdict === null) return null;
  const mark = newsMark(row.verdict, nowMs);
  const age = mark.ageClass ? AGE_RANK[mark.ageClass] ?? 0 : 0;
  switch (mark.kind) {
    case 'flame': return 30 + age;
    case 'ring': return 20 + age;
    case 'pending': return 15;
    case 'negative': return 10;
    case 'routine': return 5;
    default: return 0;
  }
}

function value(row: FocusRow, key: FocusSortKey, nowMs: number): number | string | null {
  switch (key) {
    case 'symbol': return row.symbol;
    case 'price': return row.price;
    case 'gap': return row.gapPct;
    case 'news': return focusNewsRank(row, nowMs);
  }
}

function compare(a: number | string, b: number | string): number {
  if (typeof a === 'string' && typeof b === 'string') return a.localeCompare(b);
  return (a as number) - (b as number);
}

/** Rows in `sort` order; a stable sort, so ties keep the list's own order --
 * except news, whose ties rank by the biggest % first. Unsorted returns the rows. */
export function sortFocusRows(rows: readonly FocusRow[], sort: FocusSort | null, nowMs = Date.now()): FocusRow[] {
  if (!sort) return rows as FocusRow[];
  const sign = sort.dir === 'asc' ? 1 : -1;
  return rows
    .map((row, index) => ({ row, index }))
    .sort((x, y) => {
      const a = value(x.row, sort.key, nowMs);
      const b = value(y.row, sort.key, nowMs);
      if (a == null || b == null) {
        if (a != null) return -1;
        if (b != null) return 1;
      } else {
        const primary = compare(a, b) * sign;
        if (primary !== 0) return primary;
      }
      if (sort.key === 'news') {
        const ga = x.row.gapPct;
        const gb = y.row.gapPct;
        if (ga != null && gb != null && ga !== gb) return gb - ga;
        if (ga != null && gb == null) return -1;
        if (gb != null && ga == null) return 1;
      }
      return x.index - y.index;
    })
    .map(entry => entry.row);
}
