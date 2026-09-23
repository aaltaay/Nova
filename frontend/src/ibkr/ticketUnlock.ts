/**
 * The desk padlock, read from the one place it lives: the backend arm latch
 * (ADR 018, `/api/ibkr/status.armed`).
 *
 * "Unlocked" is the status poller's snapshot, which every window shares, so
 * two desk windows cannot disagree and nothing per tab can drift from the
 * server. Unlocking is `POST /api/ibkr/arm`: Live needs the operator's PIN,
 * checked by the backend against a hash in `.env`; Paper and Sim unlock in
 * one click, and a bot may unlock them through the same endpoint. Nothing
 * here stores a flag or a PIN. Unlock gates the UI's place affordance only;
 * it never bypasses the env spend gates.
 */
import { armDesk, type ArmDeskResult } from './armDesk';
import { getIbkrStatusSnapshot, subscribeIbkrStatus } from './ibkrStatusPoller';

/** True only while the backend reports the desk armed. */
export function readTicketSessionUnlocked(): boolean {
  return getIbkrStatusSnapshot().armed === true;
}

/** Called on every status snapshot change (lock, unlock, restart, venue). */
export function subscribeTicketSessionUnlock(listener: () => void): () => void {
  return subscribeIbkrStatus(listener);
}

/** Live asks for the PIN; an unreported answer (older API, no status yet) counts as Live. */
export function unlockNeedsPin(): boolean {
  return getIbkrStatusSnapshot().arm_requires_pin !== false;
}

/** True only when the backend says the Live PIN hash is missing from `.env`. */
export function livePinMissing(): boolean {
  return getIbkrStatusSnapshot().live_arm_pin_set === false;
}

/** Arm the desk; `pin` is required on Live and ignored elsewhere. */
export function unlockTicketSession(pin?: string): Promise<ArmDeskResult> {
  return armDesk(true, pin);
}

/** Disarm the desk. Always allowed; never throws. */
export function lockTicketSession(): Promise<ArmDeskResult> {
  return armDesk(false);
}
