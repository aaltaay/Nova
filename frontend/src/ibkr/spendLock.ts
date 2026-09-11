/**
 * Spend-lock reading of `/api/ibkr/status.spend_status` (D-038 / D-013).
 *
 * Backend truth lives in `backend/ibkr/safety.py`. Any status that is not an
 * explicit `*_armed` is locked — a new locked state added on the backend must
 * fail closed in the UI instead of reading as armed.
 */

const ARMED_STATUSES = new Set(['paper_armed', 'live_armed']);

const LOCK_REASONS: Record<string, string> = {
  locked: 'Orders locked — enable IBKR orders in Nova settings/environment',
  locked_live_unconfirmed:
    'Live orders locked — explicit live confirmation is required',
  locked_account_unconfirmed:
    'Orders locked — the IB account class behind this Gateway is not confirmed yet',
};

/** True when the backend will reject a place. Unknown/absent status is locked. */
export function isSpendLocked(spendStatus?: string | null): boolean {
  return !ARMED_STATUSES.has((spendStatus ?? '').trim());
}

/** Operator-facing reason for the lock, or null when spending is armed. */
export function spendLockReason(
  spendStatus?: string | null,
  backendReason?: string | null,
): string | null {
  if (!isSpendLocked(spendStatus)) return null;
  const trimmed = (backendReason ?? '').trim();
  if (trimmed) return trimmed;
  return (
    LOCK_REASONS[(spendStatus ?? '').trim()]
    ?? 'Orders locked by IBKR environment safety settings'
  );
}

/** Short chip label for the Trading header. */
export function spendStatusLabel(spendStatus?: string | null): string {
  if (isSpendLocked(spendStatus)) return 'ORDERS LOCKED — no spends';
  return spendStatus === 'live_armed' ? 'LIVE ORDERS ARMED' : 'PAPER ORDERS ON';
}
