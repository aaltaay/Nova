/**
 * What the workspace may say about IB Gateway from the shared status poll.
 *
 * QA D10 (2026-09-22): with the API down, a status route failing or the
 * first poll still pending, `transport_connected === true` turned an unknown
 * into "disconnected" -- the red "IB Gateway login" banner, "Connect IB
 * Gateway" and "Set IBKR_ENABLED=true" all blamed the Gateway for an API that
 * never answered. Unknown stays unknown: until a current answer exists the
 * transport is undefined and the ports / hint say nothing.
 *
 * Pure: no module state.
 */
import type { DeskVenue } from '../constantGroups/desk_venue';
import { deskVenueOf } from '../ibkr/deskVenue';
import type { IbkrClientStatus } from '../ibkr/useIbkrStatus';

export interface IbkrStatusView {
  ibkrStatusKnown: boolean;
  ibkrStatusError: string | null;
  ibkrTransportConnected: boolean | undefined;
  ibkrPortsDark: boolean;
  ibkrDisconnectHint: string | null;
  deskVenue: DeskVenue | null;
}

type StatusInput = Pick<
  IbkrClientStatus,
  | 'clientReady'
  | 'stale'
  | 'statusError'
  | 'transport_connected'
  | 'preferred_port_reachable'
  | 'alternate_port_reachable'
  | 'disconnect_hint'
  | 'venue'
  | 'mode'
>;

/** True once a poll answered and its answer is current (not pending, not failing). */
export function ibkrStatusKnown(status: Pick<IbkrClientStatus, 'clientReady' | 'stale'>): boolean {
  return status.clientReady === true && status.stale !== true;
}

export function ibkrStatusView(status: StatusInput): IbkrStatusView {
  const known = ibkrStatusKnown(status);
  return {
    ibkrStatusKnown: known,
    ibkrStatusError: known ? null : status.statusError ?? null,
    ibkrTransportConnected: known && typeof status.transport_connected === 'boolean'
      ? status.transport_connected
      : undefined,
    ibkrPortsDark: known
      && status.preferred_port_reachable === false
      && status.alternate_port_reachable === false,
    ibkrDisconnectHint: known ? status.disconnect_hint ?? null : null,
    deskVenue: deskVenueOf(status),
  };
}
