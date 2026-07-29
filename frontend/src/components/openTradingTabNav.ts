/**
 * Ask the dashboard shell to show Account / Trading (orders).
 * Uses a pending latch so the request survives Trader → Scanner remount
 * (DashboardPage is unmounted while Trader tabs are open).
 */
import { GLOBAL_BAR_OPEN_TRADING_TAB_EVENT } from '../constants';

let pendingOpenTradingTab = false;

export function requestOpenTradingTab(): void {
  pendingOpenTradingTab = true;
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new Event(GLOBAL_BAR_OPEN_TRADING_TAB_EVENT));
}

/** True once; DashboardPage calls this on mount and on the event. */
export function consumeOpenTradingTabRequest(): boolean {
  if (!pendingOpenTradingTab) return false;
  pendingOpenTradingTab = false;
  return true;
}
