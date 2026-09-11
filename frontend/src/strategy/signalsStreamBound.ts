/** Cap the live signals list so a day-long desk cannot grow without bound. */
export function prependBounded<T>(item: T, prev: T[], max: number): T[] {
  const cap = Math.max(1, max);
  return [item, ...prev].slice(0, cap);
}
