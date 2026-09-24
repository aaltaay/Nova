/**
 * Click-to-sort for every table on the desk: one rule, so a header reads the
 * same everywhere.
 *
 * - The first click on a column sorts text A to Z and everything else
 *   highest first (a column may name its own first direction).
 * - A second click on the same column flips it.
 * - A third click returns to the table's own order (rank, newest first, ...).
 * - A missing value (null, undefined, NaN, '') sorts last in both directions;
 *   it is never read as zero.
 * - The sort is stable: ties keep the table's own order.
 */

export type SortDir = 'asc' | 'desc';

export interface TableSort {
  key: string;
  dir: SortDir;
}

/** What a column sorts on. Booleans sort true above false when highest first. */
export type SortValue = number | string | boolean | null | undefined;

/** A column's sort value, or the value plus its first-click direction. */
export type SortColumn<T> =
  | ((row: T) => SortValue)
  | { value: (row: T) => SortValue; first?: SortDir };

export type SortColumns<T> = Readonly<Record<string, SortColumn<T>>>;

function accessor<T>(column: SortColumn<T>): (row: T) => SortValue {
  return typeof column === 'function' ? column : column.value;
}

/** The value a row sorts on, with every kind of "missing" folded to null. */
function comparable(value: SortValue): number | string | null {
  if (value == null) return null;
  if (typeof value === 'boolean') return value ? 1 : 0;
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  const text = value.trim();
  return text === '' ? null : text;
}

/** Numbers compare as numbers; text compares case-blind with digits read as
 * numbers ("A2" before "A10"). A number sorts before text. */
export function compareSortValues(a: number | string, b: number | string): number {
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  if (typeof a === 'number') return -1;
  if (typeof b === 'number') return 1;
  return a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' });
}

/** The direction a column's first click sorts in: the column's own, else A to
 * Z when its values are text, else highest first. */
export function firstSortDir<T>(column: SortColumn<T> | undefined, rows: readonly T[]): SortDir {
  if (column && typeof column !== 'function' && column.first) return column.first;
  if (!column) return 'desc';
  const read = accessor(column);
  for (const row of rows) {
    const value = comparable(read(row));
    if (value != null) return typeof value === 'string' ? 'asc' : 'desc';
  }
  return 'desc';
}

/** One header click: a new column starts at `first`, the same column flips
 * once, and the click after that returns to the table's own order (null). */
export function nextTableSort(current: TableSort | null, key: string, first: SortDir): TableSort | null {
  if (!current || current.key !== key) return { key, dir: first };
  if (current.dir === first) return { key, dir: first === 'asc' ? 'desc' : 'asc' };
  return null;
}

/** A stored sort, or null when it is missing or malformed. */
export function parseTableSort(raw: unknown): TableSort | null {
  if (!raw || typeof raw !== 'object') return null;
  const { key, dir } = raw as Partial<TableSort>;
  if (typeof key !== 'string' || !key || (dir !== 'asc' && dir !== 'desc')) return null;
  return { key, dir };
}

/** Rows in `sort` order. No sort, or a column the table no longer has,
 * returns the rows as given. */
export function sortTableRows<T>(rows: readonly T[], sort: TableSort | null, columns: SortColumns<T>): T[] {
  const column = sort ? columns[sort.key] : undefined;
  if (!sort || !column) return rows as T[];
  const read = accessor(column);
  const sign = sort.dir === 'asc' ? 1 : -1;
  return rows
    .map((row, index) => ({ row, index, value: comparable(read(row)) }))
    .sort((x, y) => {
      if (x.value == null || y.value == null) {
        if (x.value != null) return -1;
        if (y.value != null) return 1;
        return x.index - y.index;
      }
      return compareSortValues(x.value, y.value) * sign || x.index - y.index;
    })
    .map(entry => entry.row);
}

/** `aria-sort` for a column header. */
export function ariaSortFor(sort: TableSort | null, key: string): 'ascending' | 'descending' | 'none' {
  if (!sort || sort.key !== key) return 'none';
  return sort.dir === 'asc' ? 'ascending' : 'descending';
}
