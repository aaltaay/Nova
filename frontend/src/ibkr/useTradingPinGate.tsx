/**
 * Promise-based PIN unlock for user-initiated spend actions (Flatten, etc.).
 * Same session key as header lock / Manual Order ticket.
 */
import { useCallback, useRef, useState, type ReactNode } from 'react';
import { TradingPinDialog } from './TradingPinDialog';
import {
  readTicketSessionUnlocked,
  tryUnlockTicketSession,
} from './ticketUnlock';

export function useTradingPinGate(): {
  ensureUnlocked: () => Promise<boolean>;
  pinDialog: ReactNode;
} {
  const [open, setOpen] = useState(false);
  const resolveRef = useRef<((ok: boolean) => void) | null>(null);

  const finish = useCallback((ok: boolean) => {
    setOpen(false);
    const resolve = resolveRef.current;
    resolveRef.current = null;
    resolve?.(ok);
  }, []);

  const ensureUnlocked = useCallback((): Promise<boolean> => {
    if (readTicketSessionUnlocked()) return Promise.resolve(true);
    setOpen(true);
    return new Promise<boolean>((resolve) => {
      resolveRef.current = resolve;
    });
  }, []);

  const pinDialog = (
    <TradingPinDialog
      open={open}
      onCancel={() => finish(false)}
      onSubmit={(pin) => {
        const ok = tryUnlockTicketSession(pin);
        if (ok) finish(true);
        return ok;
      }}
    />
  );

  return { ensureUnlocked, pinDialog };
}
