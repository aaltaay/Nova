/** Stale-request rejection for chart bar fetches (ADR 005). */

export function isCurrentBarsRequest(
  requestVersion: number,
  currentVersion: number,
): boolean {
  return requestVersion === currentVersion;
}
