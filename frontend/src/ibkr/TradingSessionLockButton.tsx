/**
 * GlobalAppBar lock / unlock icon — same PIN session gate as Manual Order
 * "Unlock Trading" / Place an order. Does not touch IBKR spend env gates.
 */
import { useEffect, useState } from 'react';
import { Lock, LockOpen } from 'lucide-react';
import {
  TICKER_TRADE_LOCK_ICON_ARIA_LOCKED,
  TICKER_TRADE_LOCK_ICON_ARIA_UNLOCKED,
  TICKER_TRADE_LOCK_ICON_LOCKED_TITLE,
  TICKER_TRADE_LOCK_ICON_UNLOCKED_TITLE,
} from '../constants';
import { TradingPinDialog } from './TradingPinDialog';
import {
  readTicketSessionUnlocked,
  subscribeTicketSessionUnlock,
  tryUnlockTicketSession,
  writeTicketSessionUnlocked,
} from './ticketUnlock';

export function TradingSessionLockButton() {
  const [unlocked, setUnlocked] = useState(readTicketSessionUnlocked);
  const [pinOpen, setPinOpen] = useState(false);

  useEffect(() => {
    const sync = () => setUnlocked(readTicketSessionUnlocked());
    sync();
    return subscribeTicketSessionUnlock(sync);
  }, []);

  function onClick() {
    if (unlocked) {
      writeTicketSessionUnlocked(false);
      setPinOpen(false);
      return;
    }
    setPinOpen(true);
  }

  return (
    <>
      <button
        type="button"
        className={`global-app-bar__trade-lock${unlocked ? ' is-unlocked' : ' is-locked'}`}
        title={
          unlocked
            ? TICKER_TRADE_LOCK_ICON_UNLOCKED_TITLE
            : TICKER_TRADE_LOCK_ICON_LOCKED_TITLE
        }
        aria-label={
          unlocked
            ? TICKER_TRADE_LOCK_ICON_ARIA_UNLOCKED
            : TICKER_TRADE_LOCK_ICON_ARIA_LOCKED
        }
        aria-pressed={unlocked}
        data-testid="global-bar-trade-lock"
        onClick={onClick}
      >
        {unlocked ? (
          <LockOpen className="global-app-bar__trade-lock-icon" aria-hidden />
        ) : (
          <Lock className="global-app-bar__trade-lock-icon" aria-hidden />
        )}
      </button>
      <TradingPinDialog
        open={pinOpen}
        onCancel={() => setPinOpen(false)}
        onSubmit={(pin) => {
          const ok = tryUnlockTicketSession(pin);
          if (ok) setPinOpen(false);
          return ok;
        }}
      />
    </>
  );
}
