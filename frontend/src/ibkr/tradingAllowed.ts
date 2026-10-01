/**
 * Desk SSOT for whether places are allowed (looks vs is).
 *
 * Backend `/api/ibkr/status.trading_allowed` is the spend permission + Gateway
 * + the padlock (the backend arm latch, ADR 018) -- the same gate place_order
 * meets. `sessionUnlocked` is that same padlock, read through ticketUnlock
 * (`/api/ibkr/status.armed`), so Activate, padlock, ticket, and Nova Actions
 * read one gate. Flatten / KILL stay protective.
 *
 * One latch, counted once (spec D, 2026-09-30): when the backend refuses only
 * because the desk is disarmed (`spend_status: locked_disarmed` -- the env
 * permits spending), that is the padlock, never also a "spend" lock. The
 * blocker is named `pin` for history: there is no client-side PIN any more --
 * it is the padlock, and the Live PIN is checked by the backend when arming.
 *
 * It is the gate for the orders the backend holds to the arm latch: every
 * order but a cancel or a protective source. Nova Actions use it for those
 * kinds only; their cancels and whole-position flattens answer to the locks
 * the backend holds them to (`hotkeys/runNovaAction.ts`, ADR 018 decision 4,
 * #548).
 */
import {
  BOT_STATE_ACTIVE,
  BOT_STATE_NOT_ACTIVE,
  NOVA_ACTION_PIN_LOCKED_MESSAGE,
  NOVA_ACTION_SPEND_LOCKED_MESSAGE,
} from '../constants';
import { isDisarmed, isSpendLocked, spendLockReason } from './spendLock';

/** `pin` is the padlock (the backend arm latch); `spend` an env / account gate; `disconnected` the Gateway. */
export type TradingBlocker = 'disconnected' | 'spend' | 'pin';

export type TradingAllowed = {
  allowed: boolean;
  reason: string | null;
  blockers: TradingBlocker[];
};

export type TradingAllowedInput = {
  connected?: boolean;
  spendStatus?: string | null;
  spendReason?: string | null;
  sessionUnlocked: boolean;
  /** When the status payload includes trading_allowed, prefer it. */
  backendAllowed?: boolean | null;
  backendReason?: string | null;
};

export function evaluateTradingAllowed(input: TradingAllowedInput): TradingAllowed {
  const blockers: TradingBlocker[] = [];
  let reason: string | null = null;

  if (input.connected === false) {
    blockers.push('disconnected');
    reason = 'IBKR disconnected -- connect Gateway first';
  }

  const backendKnown = input.backendAllowed === true || input.backendAllowed === false;
  const spendBlocked = backendKnown
    ? input.backendAllowed === false
    : isSpendLocked(input.spendStatus);
  if (spendBlocked && !blockers.includes('disconnected')) {
    const backendWhy = (input.backendReason ?? '').trim();
    // The env permits spending and the backend refuses for the latch alone: that is the
    // padlock (`pin`), not a second "spend" lock. Any other refusal stays its own blocker.
    const padlockOnly = isDisarmed(input.spendStatus) && (!backendWhy || /disarm/i.test(backendWhy));
    blockers.push(padlockOnly ? 'pin' : 'spend');
    reason =
      backendWhy
      || spendLockReason(input.spendStatus, input.spendReason)
      || NOVA_ACTION_SPEND_LOCKED_MESSAGE;
  }

  if (!input.sessionUnlocked && !blockers.includes('pin')) {
    blockers.push('pin');
    if (reason == null) reason = NOVA_ACTION_PIN_LOCKED_MESSAGE;
  }

  return { allowed: blockers.length === 0, reason, blockers };
}

export function botArmDisplayState(
  armed: boolean,
  gate: TradingAllowed,
): { label: string; looksActive: boolean } {
  if (armed && gate.allowed) {
    return { label: BOT_STATE_ACTIVE, looksActive: true };
  }
  if (armed && !gate.allowed) {
    return {
      label: `${BOT_STATE_ACTIVE} -- ${gate.reason ?? 'places blocked'}`,
      looksActive: false,
    };
  }
  return { label: BOT_STATE_NOT_ACTIVE, looksActive: false };
}

export function padlockLooksUnlocked(gate: TradingAllowed): boolean {
  return gate.allowed;
}
