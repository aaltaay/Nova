/**
 * Desk SSOT for whether places are allowed (looks vs is).
 *
 * Backend `/api/ibkr/status.trading_allowed` is spend + Gateway (same as
 * place_order). This helper AND-s the padlock (the backend arm latch,
 * `/api/ibkr/status.armed`, read through ticketUnlock) so Activate, padlock,
 * ticket, and Nova Actions read one gate. Flatten / KILL stay protective.
 */
import {
  BOT_STATE_ACTIVE,
  BOT_STATE_NOT_ACTIVE,
  NOVA_ACTION_PIN_LOCKED_MESSAGE,
  NOVA_ACTION_SPEND_LOCKED_MESSAGE,
} from '../constants';
import { isSpendLocked, spendLockReason } from './spendLock';

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
    blockers.push('spend');
    reason =
      (input.backendReason ?? '').trim()
      || spendLockReason(input.spendStatus, input.spendReason)
      || NOVA_ACTION_SPEND_LOCKED_MESSAGE;
  }

  if (!input.sessionUnlocked) {
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
