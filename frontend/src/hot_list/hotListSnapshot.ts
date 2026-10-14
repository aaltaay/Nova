/** Equality of the complete normalized hot-list view, including row and yesterday ordering (#797). */
import type { HotListView } from './types';

/** These normalized objects contain only primitive fields. Compare keys too, so new fields participate. */
function sameFields<T extends object>(a: T, b: T): boolean {
  const keys = Object.keys(a) as Array<keyof T>;
  return keys.length === Object.keys(b).length
    && keys.every(key => Object.prototype.hasOwnProperty.call(b, key) && Object.is(a[key], b[key]));
}

export function sameHotListView(a: HotListView | null, b: HotListView | null): boolean {
  if (a === b) return true;
  if (a === null || b === null) return false;
  const { auto: aAuto, entries: aEntries, yesterday: aYesterday, ...aFields } = a;
  const { auto: bAuto, entries: bEntries, yesterday: bYesterday, ...bFields } = b;
  return sameFields(aFields, bFields) && sameFields(aAuto, bAuto)
    && aEntries.length === bEntries.length
    && aEntries.every((entry, i) => sameFields(entry, bEntries[i]))
    && aYesterday.length === bYesterday.length
    && aYesterday.every((symbol, i) => symbol === bYesterday[i]);
}
