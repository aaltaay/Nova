/**
 * Closed Orders “just finished” highlight — completion within a short window.
 * Uses activity time (updated_at / cancel-or-fill), not submitted_at alone.
 */

export function isClosedOrderRecent(
  activityIso: string | null | undefined,
  nowMs: number,
  windowMs: number,
): boolean {
  if (!activityIso || !(windowMs > 0)) return false;
  const completedMs = Date.parse(activityIso);
  if (!Number.isFinite(completedMs)) return false;
  const ageMs = nowMs - completedMs;
  // Ignore clock-skew futures; only highlight true recent past.
  return ageMs >= 0 && ageMs <= windowMs;
}
