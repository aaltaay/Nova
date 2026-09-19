/** Last successful /api/ibkr/status for this browser tab (not a live feed). */
import { IBKR_STATUS_SESSION_KEY } from '../constants';
import type { IbkrStatus } from './types';

export function readLastIbkrStatus(): IbkrStatus | null {
  try {
    const raw = sessionStorage.getItem(IBKR_STATUS_SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as IbkrStatus;
    if (typeof parsed?.connected !== 'boolean' || typeof parsed?.mode !== 'string') {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function writeLastIbkrStatus(status: IbkrStatus): void {
  try {
    sessionStorage.setItem(
      IBKR_STATUS_SESSION_KEY,
      JSON.stringify({
        enabled: status.enabled,
        connected: status.connected,
        transport_connected: status.transport_connected,
        session_reason: status.session_reason,
        mode: status.mode,
        gateway_mode: status.gateway_mode,
        broker_account_kind: status.broker_account_kind,
        intentional_gateway_mode: status.intentional_gateway_mode,
        market_data_delayed: status.market_data_delayed,
        orders_enabled: status.orders_enabled,
        spend_status: status.spend_status,
        armed_for_account_kind: status.armed_for_account_kind ?? null,
        spend_locked_reason: status.spend_locked_reason ?? null,
        trading_allowed: status.trading_allowed,
        trading_allowed_reason: status.trading_allowed_reason ?? null,
        disconnect_hint: status.disconnect_hint ?? null,
        preferred_port_reachable: status.preferred_port_reachable,
        alternate_port_reachable: status.alternate_port_reachable,
      }),
    );
  } catch {
    /* private mode / quota */
  }
}
