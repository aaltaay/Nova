/**
 * Local Open-ticket session unlock (PIN gate).
 * Does not bypass IBKR_ORDERS_ENABLED / live confirmation — only the UI submit affordance.
 */
import {
  TICKER_TRADE_UNLOCK_PIN,
  TICKER_TRADE_UNLOCK_SESSION_KEY,
} from '../constants';

export function readTicketSessionUnlocked(): boolean {
  try {
    return sessionStorage.getItem(TICKER_TRADE_UNLOCK_SESSION_KEY) === '1';
  } catch {
    return false;
  }
}

export function writeTicketSessionUnlocked(unlocked: boolean): void {
  try {
    if (unlocked) {
      sessionStorage.setItem(TICKER_TRADE_UNLOCK_SESSION_KEY, '1');
    } else {
      sessionStorage.removeItem(TICKER_TRADE_UNLOCK_SESSION_KEY);
    }
  } catch {
    /* private mode / quota */
  }
}

/** Returns true when `pin` matches the configured local unlock code. */
export function tryUnlockTicketSession(pin: string): boolean {
  const ok = pin.trim() === TICKER_TRADE_UNLOCK_PIN;
  if (ok) writeTicketSessionUnlocked(true);
  return ok;
}
