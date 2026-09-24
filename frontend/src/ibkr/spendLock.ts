/**
 * Spend-lock reading of `/api/ibkr/status.spend_status` (D-038 / D-013).
 *
 * Backend truth lives in `backend/ibkr/safety.py`. Any status that is not an
 * explicit `*_armed` is locked — a new locked state added on the backend must
 * fail closed in the UI instead of reading as armed.
 */

const ARMED_STATUSES = new Set(['paper_armed', 'live_armed', 'sim_armed']);
// ADR 018: the env permits spending; only this session's arm latch is off.
const DISARMED_STATUS = 'locked_disarmed';

const LOCK_REASONS: Record<string, string> = {
  locked: 'Orders locked — enable IBKR orders in Nova settings/environment',
  locked_live_unconfirmed:
    'Live orders locked — explicit live confirmation is required',
  locked_account_unconfirmed:
    'Orders locked — the IB account class behind this Gateway is not confirmed yet',
  // ADR 018: the env still permits spending; this process is not armed.
  locked_disarmed:
    'Desk is disarmed — unlock the padlock to arm trading in this session',
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

/** True when the arm latch is the only lock: the env permits spending, this session is not armed. */
export function isDisarmed(spendStatus?: string | null): boolean {
  return (spendStatus ?? '').trim() === DISARMED_STATUS;
}

/**
 * The spend lock a Flatten obeys: why it cannot send, or null.
 *
 * Flatten is sent as the protective `flatten` source, which the backend's arm
 * latch never holds (`ibkr/safety.PROTECTIVE_SOURCES`), so a disarmed desk can
 * always get flat (ADR 018). Every other lock -- the env gates, an unconfirmed
 * account class, a status not known yet -- refuses a flatten on Live too, so it
 * still holds.
 */
export function flattenSpendLockReason(spendStatus?: string | null): string | null {
  return isDisarmed(spendStatus) ? null : spendLockReason(spendStatus);
}

/** Short chip label for the Trading header. */
export function spendStatusLabel(spendStatus?: string | null): string {
  // ADR 018: disarmed is not the same as locked by the environment, and the
  // operator's next action differs -- arm the desk vs change a gate.
  if (spendStatus === 'locked_disarmed') return 'DISARMED — arm to trade';
  if (isSpendLocked(spendStatus)) return 'ORDERS LOCKED — no spends';
  if (spendStatus === 'live_armed') return 'LIVE ORDERS ARMED';
  if (spendStatus === 'sim_armed') return 'SIM ORDERS (PRACTICE)';
  return 'PAPER ORDERS ON';
}
