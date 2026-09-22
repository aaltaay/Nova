/**
 * Ask the dashboard shell to show Account / Trading (orders).
 * Thin alias over the nav-rail tab latch (workspace/navRailStore) so the
 * Working menu and Settings keep one door; the latch survives a Trader →
 * Scanner remount (DashboardPage is unmounted while Trader tabs are open).
 */
import {
  consumeScannerTabRequest,
  peekScannerTabRequest,
  requestScannerTab,
} from '../workspace/navRailStore';

export function requestOpenTradingTab(): void {
  requestScannerTab('trading');
}

/** True once when the pending request is the trading tab. */
export function consumeOpenTradingTabRequest(): boolean {
  if (peekScannerTabRequest() !== 'trading') return false;
  return consumeScannerTabRequest() === 'trading';
}
