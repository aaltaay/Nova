/**
 * Local Open-ticket session unlock (PIN gate).
 * Does not bypass IBKR_ORDERS_ENABLED / live confirmation -- only the UI submit affordance.
 * Same-window listeners use a CustomEvent. Peer desk windows (pop-out) get
 * BroadcastChannel plus a localStorage storage-event echo.
 */
import {
  TICKER_TRADE_UNLOCK_CHANNEL,
  TICKER_TRADE_UNLOCK_PIN,
  TICKER_TRADE_UNLOCK_SESSION_KEY,
  TICKER_TRADE_UNLOCK_SYNC_KEY,
} from '../constants';

const CHANGE_EVENT = 'nova-ticket-session-unlock';

type UnlockChannel = {
  postMessage: (data: unknown) => void;
  addEventListener: (type: 'message', fn: (ev: MessageEvent) => void) => void;
};

let syncChannel: UnlockChannel | null | undefined;

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
  ensureUnlockSync();
  window.addEventListener(CHANGE_EVENT, listener);
  return () => window.removeEventListener(CHANGE_EVENT, listener);
}

export function writeTicketSessionUnlocked(unlocked: boolean): void {
  applyUnlocked(unlocked, true);
}

/** Returns true when `pin` matches the configured local unlock code. */
export function tryUnlockTicketSession(pin: string): boolean {
  const ok = pin.trim() === TICKER_TRADE_UNLOCK_PIN;
  if (ok) writeTicketSessionUnlocked(true);
  return ok;
}

function applyUnlocked(unlocked: boolean, echo: boolean): void {
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
  // ADR 018: the PIN is the challenge, the backend latch is the gate. Only the
  // window the operator acted in posts -- peers apply the echo locally, so a
  // BroadcastChannel round trip cannot arm a desk nobody touched.
  if (echo) {
    void armDeskBestEffort(unlocked);
    echoUnlocked(unlocked);
  }
}

function armDeskBestEffort(unlocked: boolean): Promise<unknown> {
  // Imported lazily so unit tests that exercise the local session flag do not
  // need a fetch stub, and a missing backend never breaks the padlock.
  return import('./armDesk')
    .then((m) => m.armDesk(unlocked))
    .catch(() => false);
}

function echoUnlocked(unlocked: boolean): void {
  const channel = ensureUnlockSync();
  try {
    channel?.postMessage({ unlocked });
  } catch {
    /* channel closed */
  }
  try {
    localStorage.setItem(
      TICKER_TRADE_UNLOCK_SYNC_KEY,
      JSON.stringify({ unlocked, t: Date.now() }),
    );
  } catch {
    /* private mode / quota */
  }
}

function onPeerMessage(ev: MessageEvent): void {
  const unlocked = ev.data?.unlocked;
  if (unlocked === true || unlocked === false) {
    applyUnlocked(unlocked, false);
  }
}

function onPeerStorage(ev: StorageEvent): void {
  if (ev.key !== TICKER_TRADE_UNLOCK_SYNC_KEY || !ev.newValue) return;
  try {
    const parsed = JSON.parse(ev.newValue) as { unlocked?: unknown };
    if (parsed.unlocked === true || parsed.unlocked === false) {
      applyUnlocked(parsed.unlocked, false);
    }
  } catch {
    /* ignore malformed peer payload */
  }
}

function ensureUnlockSync(): UnlockChannel | null {
  if (syncChannel !== undefined) return syncChannel;
  syncChannel = null;
  if (typeof BroadcastChannel !== 'undefined') {
    try {
      const channel = new BroadcastChannel(TICKER_TRADE_UNLOCK_CHANNEL);
      channel.addEventListener('message', onPeerMessage);
      syncChannel = channel;
    } catch {
      syncChannel = null;
    }
  }
  if (typeof window !== 'undefined') {
    window.addEventListener('storage', onPeerStorage);
  }
  return syncChannel;
}
