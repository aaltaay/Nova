/**
 * One idempotency key per user gesture (ADR 007 / D-011).
 *
 * The backend ledger dedupes on `idempotency_key`, so a key minted per HTTP
 * call gives that protection away: a gesture that reaches the place endpoint
 * twice — a double-clicked Submit, a re-fired hotkey, a retried confirm —
 * arrives as two unrelated orders. Mint the key when the gesture starts and
 * reuse it for every attempt that gesture makes.
 */

export function newGestureKey(prefix: string): string {
  const unique =
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `${prefix}:${unique}`;
}
