/**
 * The one unlock flow every door uses (padlock, ticket, Flatten, the Bots page).
 *
 * `ensureUnlocked()` resolves true once the backend reports the desk armed:
 * already armed -> true at once; Paper / Sim -> one POST /api/ibkr/arm, no
 * PIN; Live (or an API that does not say) -> the PIN dialog, whose digits go
 * to the backend and whose refusal is the backend's own words. Nothing here
 * decides whether a PIN is right.
 */
import { useCallback, useRef, useState, type ReactNode } from 'react';
import {
  TICKER_TRADE_LIVE_PIN_NOT_SET,
  TICKER_TRADE_UNLOCK_REFUSED_TITLE,
} from '../constants';
import { alertApp } from '../ux';
import { TradingPinDialog } from './TradingPinDialog';
import {
  livePinMissing,
  readTicketSessionUnlocked,
  unlockNeedsPin,
  unlockTicketSession,
} from './ticketUnlock';

function sayStillLocked(message: string | null): void {
  console.warn('[Nova] desk unlock refused', message);
  if (!message) return;
  alertApp({ title: TICKER_TRADE_UNLOCK_REFUSED_TITLE, message, tone: 'danger' }).catch((err) => {
    console.warn('[Nova] could not show the unlock refusal', err);
  });
}

export function useTradingPinGate(): {
  ensureUnlocked: () => Promise<boolean>;
  pinDialog: ReactNode;
} {
  const [open, setOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const resolveRef = useRef<((ok: boolean) => void) | null>(null);

  const finish = useCallback((ok: boolean) => {
    setOpen(false);
    const resolve = resolveRef.current;
    resolveRef.current = null;
    resolve?.(ok);
  }, []);

  const ensureUnlocked = useCallback(async (): Promise<boolean> => {
    if (readTicketSessionUnlocked()) return true;
    if (!unlockNeedsPin()) {
      const res = await unlockTicketSession();
      if (!res.ok) sayStillLocked(res.message);
      return res.ok;
    }
    // A second ask while the prompt is open replaces the first; the first is not left hanging.
    resolveRef.current?.(false);
    setNotice(livePinMissing() ? TICKER_TRADE_LIVE_PIN_NOT_SET : null);
    setOpen(true);
    return new Promise<boolean>((resolve) => {
      resolveRef.current = resolve;
    });
  }, []);

  const submitPin = useCallback(async (pin: string): Promise<string | null> => {
    const res = await unlockTicketSession(pin);
    if (res.ok) {
      finish(true);
      return null;
    }
    return res.message ?? res.code ?? TICKER_TRADE_UNLOCK_REFUSED_TITLE;
  }, [finish]);

  const pinDialog = (
    <TradingPinDialog
      open={open}
      notice={notice}
      onCancel={() => finish(false)}
      onSubmit={submitPin}
    />
  );

  return { ensureUnlocked, pinDialog };
}
