/**
 * Primitive guards for the Sim / replay / capture payload parsers (QA 2026-09-22,
 * C6 / C7 / C9 / C13). A payload arrives as `unknown`; every field a view calls a
 * method on, destructures or iterates is checked here once, at the boundary, so
 * one malformed field reads as an absence instead of replacing the desk.
 */

export type Obj = Record<string, unknown>;

export const isObject = (value: unknown): value is Obj =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

/** A finite number, else undefined. */
export const finite = (value: unknown): number | undefined =>
  typeof value === 'number' && Number.isFinite(value) ? value : undefined;

/** A finite number, else null. */
export const finiteOrNull = (value: unknown): number | null => finite(value) ?? null;

/** A string, else undefined. */
export const text = (value: unknown): string | undefined => (typeof value === 'string' ? value : undefined);

/** A string, else null. */
export const textOrNull = (value: unknown): string | null => text(value) ?? null;

/** A boolean, else undefined. */
export const flag = (value: unknown): boolean | undefined => (typeof value === 'boolean' ? value : undefined);

/** Objects only, from a list; anything but a list is empty. */
export const objects = (value: unknown): Obj[] => (Array.isArray(value) ? value.filter(isObject) : []);

/**
 * `[[start, end], ...]` epoch-second ranges: only two-number pairs with
 * `end > start` survive. Undefined when the field is not a list at all, so a
 * pre-range payload keeps its own fallback.
 */
export function rangePairs(value: unknown): number[][] | undefined {
  if (!Array.isArray(value)) return undefined;
  return value
    .filter((pair): pair is [number, number] => Array.isArray(pair) && pair.length === 2
      && finite(pair[0]) != null && finite(pair[1]) != null)
    .filter(([a, b]) => b > a)
    .map(([a, b]) => [a, b]);
}

/** Drop keys whose value is undefined, so an absent field stays absent. */
export function compact<T extends Obj>(value: T): T {
  return Object.fromEntries(Object.entries(value).filter(([, v]) => v !== undefined)) as T;
}
