/**
 * Live desk read of trading_allowed -- the status poll, whose `armed` is the padlock.
 */
import { useSyncExternalStore } from 'react';
import { evaluateTradingAllowed, type TradingAllowed } from './tradingAllowed';
import {
  readTicketSessionUnlocked,
  subscribeTicketSessionUnlock,
} from './ticketUnlock';
import { useIbkrStatus } from './useIbkrStatus';

const LOCKED_ON_SERVER_RENDER = () => false;

export function useDeskTradingAllowed(): TradingAllowed & {
  sessionUnlocked: boolean;
  /**
   * True once this window has its own fresh status read. A hydrated cache or
   * a failed poll cannot say whether the desk is armed now, so nothing should
   * act on "locked" (stop a bot, say) until this is true.
   */
  armKnown: boolean;
} {
  const status = useIbkrStatus();
  const sessionUnlocked = useSyncExternalStore(
    subscribeTicketSessionUnlock,
    readTicketSessionUnlocked,
    LOCKED_ON_SERVER_RENDER,
  );

  const gate = evaluateTradingAllowed({
    connected: status.connected,
    spendStatus: status.spend_status,
    spendReason: status.spend_locked_reason,
    sessionUnlocked,
    backendAllowed: status.trading_allowed,
    backendReason: status.trading_allowed_reason,
  });
  const armKnown = status.lastSuccessAt != null && !status.stale && typeof status.armed === 'boolean';
  return { ...gate, sessionUnlocked, armKnown };
}
