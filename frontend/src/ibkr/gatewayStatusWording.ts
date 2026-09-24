/**
 * What the ticket says about IB Gateway when it cannot trade (QA D10 on the
 * ticket, #459). "Connect IB Gateway" only once `/api/ibkr/status` has said
 * the Gateway is down; while that request is pending or failing, nothing is
 * known about the Gateway and the ticket says so, as the header and the depth
 * card already do. The caller that reads the status builds the fact
 * (`workspace/ibkrStatusView.ibkrStatusKnown`). Pure.
 */
import {
  TICKET_CONNECT_GATEWAY_LABEL,
  TICKET_GATEWAY_CHECKING_LABEL,
  TICKET_GATEWAY_UNKNOWN_LABEL,
  WHY_GATEWAY_NOT_CONNECTED,
  WHY_GATEWAY_STATUS_FAILED,
  WHY_GATEWAY_STATUS_PENDING,
} from '../constantGroups/trader_chrome';

export interface GatewayStatusFact {
  /** A status answer exists and is current (not pending, not failing). */
  known: boolean;
  /** Why the last status poll failed, while unknown; null while pending or known. */
  error: string | null;
}

/** A caller with no status of its own to read: `connected` is taken at its word. */
export const GATEWAY_STATUS_KNOWN: GatewayStatusFact = { known: true, error: null };

/** The reason a control locked for want of the Gateway carries in `data-why`. */
export function gatewayLockWhy(fact: GatewayStatusFact): string {
  if (fact.known) return WHY_GATEWAY_NOT_CONNECTED;
  return fact.error ? `${WHY_GATEWAY_STATUS_FAILED} (${fact.error})` : WHY_GATEWAY_STATUS_PENDING;
}

/** The Place button's label while the Gateway cannot trade. */
export function gatewayPlaceLabel(fact: GatewayStatusFact): string {
  if (fact.known) return TICKET_CONNECT_GATEWAY_LABEL;
  return fact.error ? TICKET_GATEWAY_UNKNOWN_LABEL : TICKET_GATEWAY_CHECKING_LABEL;
}
