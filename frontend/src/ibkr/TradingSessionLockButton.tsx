/**
 * GlobalAppBar lock / unlock icon -- same trading_allowed gate as Place.
 * Icon looks unlocked only when places are allowed (spend + PIN + connected).
 */
import { useState } from 'react';
import { Lock, LockOpen } from 'lucide-react';
import {
  TICKER_TRADE_LOCK_ICON_ARIA_LOCKED,
  TICKER_TRADE_LOCK_ICON_ARIA_UNLOCKED,
  TICKER_TRADE_LOCK_ICON_LOCKED_TITLE,
  TICKER_TRADE_LOCK_ICON_UNLOCKED_TITLE,
} from '../constants';
import { padlockLooksUnlocked } from './tradingAllowed';
import { TradingPinDialog } from './TradingPinDialog';
import { tryUnlockTicketSession, writeTicketSessionUnlocked } from './ticketUnlock';
import { useDeskTradingAllowed } from './useDeskTradingAllowed';

export function TradingSessionLockButton() {
  const gate = useDeskTradingAllowed();
  const [pinOpen, setPinOpen] = useState(false);
  const looksUnlocked = padlockLooksUnlocked(gate);

  function onClick() {
    if (gate.sessionUnlocked) {
      writeTicketSessionUnlocked(false);
      setPinOpen(false);
      return;
    }
    setPinOpen(true);
  }

  const lockedTitle = gate.reason
    ? `${TICKER_TRADE_LOCK_ICON_LOCKED_TITLE} ${gate.reason}`
    : TICKER_TRADE_LOCK_ICON_LOCKED_TITLE;

  return (
    <>
      <button
        type="button"
        className={`global-app-bar__trade-lock${looksUnlocked ? ' is-unlocked' : ' is-locked'}`}
        title={looksUnlocked ? TICKER_TRADE_LOCK_ICON_UNLOCKED_TITLE : lockedTitle}
        aria-label={
          looksUnlocked
            ? TICKER_TRADE_LOCK_ICON_ARIA_UNLOCKED
            : TICKER_TRADE_LOCK_ICON_ARIA_LOCKED
        }
        aria-pressed={looksUnlocked}
        data-testid="global-bar-trade-lock"
        onClick={onClick}
      >
        {looksUnlocked ? (
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
