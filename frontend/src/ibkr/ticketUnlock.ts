/**
 * Local Open-ticket session unlock (PIN gate).
 * Does not bypass IBKR_ORDERS_ENABLED / live confirmation — only the UI submit affordance.
 */
import {
  TICKER_TRADE_UNLOCK_PIN,
  TICKER_TRADE_UNLOCK_SESSION_KEY,
} from '../constants';

const CHANGE_EVENT = 'nova-ticket-session-unlock';

export function readTicketSessionUnlocked(): boolean {
  try {
    return sessionStorage.getItem(TICKER_TRADE_UNLOCK_SESSION_KEY) === '1';
  } catch {
    return false;
  }
}

/** Notify header lock icon + Manual Order ticket after unlock/lock. */
export function notifyTicketSessionUnlockChanged(): void {
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

export function subscribeTicketSessionUnlock(
  listener: () => void,
): () => void {
  window.addEventListener(CHANGE_EVENT, listener);
  return () => window.removeEventListener(CHANGE_EVENT, listener);
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
  notifyTicketSessionUnlockChanged();
}

/** Returns true when `pin` matches the configured local unlock code. */
export function tryUnlockTicketSession(pin: string): boolean {
  const ok = pin.trim() === TICKER_TRADE_UNLOCK_PIN;
  if (ok) writeTicketSessionUnlocked(true);
  return ok;
}
