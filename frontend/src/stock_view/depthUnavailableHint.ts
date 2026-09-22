/**
 * What the Stock Quote card says when Level 2 / Time & Sales cannot open.
 * "Connect IB Gateway" only once the status says the Gateway is down; while
 * the status request is pending or failing nothing is known about the
 * Gateway, so the card says that instead (QA D10, 2026-09-22). Pure.
 */
import {
  TRADER_DEPTH_CONNECT_GATEWAY,
  TRADER_DEPTH_STATUS_FAILED,
  TRADER_DEPTH_STATUS_PENDING,
} from '../constantGroups/trader_view';

export function depthUnavailableHint(statusKnown: boolean, statusError: string | null): string {
  if (statusKnown) return TRADER_DEPTH_CONNECT_GATEWAY;
  return statusError ? `${TRADER_DEPTH_STATUS_FAILED} (${statusError})` : TRADER_DEPTH_STATUS_PENDING;
}
