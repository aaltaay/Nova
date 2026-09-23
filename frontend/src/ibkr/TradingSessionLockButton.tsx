/**
 * GlobalAppBar padlock -- the backend arm latch (ADR 018), same gate as Place.
 * Looks unlocked only when places are allowed (armed + spend + connected).
 * A click while armed locks; otherwise it runs the one unlock flow
 * (one click on Paper / Sim, the Live PIN on Live).
 */
import { Lock, LockOpen } from 'lucide-react';
import {
  TICKER_TRADE_LOCK_ICON_ARIA_LOCKED,
  TICKER_TRADE_LOCK_ICON_ARIA_UNLOCKED,
} from '../constants';
import { padlockTitle } from './padlockTitle';
import { padlockLooksUnlocked } from './tradingAllowed';
import { lockTicketSession } from './ticketUnlock';
import { useDeskTradingAllowed } from './useDeskTradingAllowed';
import { useIbkrStatus } from './useIbkrStatus';
import { useTradingPinGate } from './useTradingPinGate';

export function TradingSessionLockButton() {
  const status = useIbkrStatus();
  const gate = useDeskTradingAllowed();
  const { ensureUnlocked, pinDialog } = useTradingPinGate();
  const looksUnlocked = padlockLooksUnlocked(gate);

  function onClick() {
    if (gate.sessionUnlocked) {
      void lockTicketSession();
      return;
    }
    void ensureUnlocked();
  }

  return (
    <>
      <button
        type="button"
        className={`global-app-bar__trade-lock${looksUnlocked ? ' is-unlocked' : ' is-locked'}`}
        title={padlockTitle(status, gate)}
        aria-label={
          gate.sessionUnlocked
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
      {pinDialog}
    </>
  );
}
