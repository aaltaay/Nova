/**
 * Live desk read of trading_allowed -- status poll + PIN session.
 */
import { useEffect, useState } from 'react';
import { evaluateTradingAllowed, type TradingAllowed } from './tradingAllowed';
import {
  readTicketSessionUnlocked,
  subscribeTicketSessionUnlock,
} from './ticketUnlock';
import { useIbkrStatus } from './useIbkrStatus';

export function useDeskTradingAllowed(): TradingAllowed & { sessionUnlocked: boolean } {
  const status = useIbkrStatus();
  const [sessionUnlocked, setSessionUnlocked] = useState(readTicketSessionUnlocked);

  useEffect(() => {
    const sync = () => setSessionUnlocked(readTicketSessionUnlocked());
    sync();
    return subscribeTicketSessionUnlock(sync);
  }, []);

  const gate = evaluateTradingAllowed({
    connected: status.connected,
    spendStatus: status.spend_status,
    spendReason: status.spend_locked_reason,
    sessionUnlocked,
    backendAllowed: status.trading_allowed,
    backendReason: status.trading_allowed_reason,
  });
  return { ...gate, sessionUnlocked };
}
