import { describe, expect, it } from 'vitest';
import { shouldShowGatewayLoginBanner } from '../ibkr/GatewayDisconnectedBanner';
import { ibkrStatusView } from './ibkrStatusView';

const base = {
  clientReady: true,
  stale: false,
  statusError: null,
  transport_connected: false,
  preferred_port_reachable: false,
  alternate_port_reachable: false,
  disconnect_hint: 'both_ports_unreachable',
  venue: 'live' as const,
  mode: 'disconnected' as const,
};

function banner(view: ReturnType<typeof ibkrStatusView>): boolean {
  return shouldShowGatewayLoginBanner({
    discoveryProvider: 'ibkr',
    ibkrConnected: false,
    ibkrTransportConnected: view.ibkrTransportConnected,
    ibkrPortsDark: view.ibkrPortsDark,
    ibkrDisconnectHint: view.ibkrDisconnectHint,
  });
}

describe('ibkrStatusView: unknown stays unknown (QA D10)', () => {
  it('states a proven outage from a current answer', () => {
    const view = ibkrStatusView(base);
    expect(view.ibkrStatusKnown).toBe(true);
    expect(view.ibkrTransportConnected).toBe(false);
    expect(view.ibkrPortsDark).toBe(true);
    expect(banner(view)).toBe(true);
  });

  it('says nothing about the Gateway while the first poll is pending', () => {
    const view = ibkrStatusView({ ...base, clientReady: false });
    expect(view.ibkrStatusKnown).toBe(false);
    expect(view.ibkrStatusError).toBeNull();
    expect(view.ibkrTransportConnected).toBeUndefined();
    expect(view.ibkrPortsDark).toBe(false);
    expect(view.ibkrDisconnectHint).toBeNull();
    expect(banner(view)).toBe(false);
  });

  it('says nothing about the Gateway while the status route fails, and names why', () => {
    const view = ibkrStatusView({ ...base, stale: true, statusError: 'HTTP 500' });
    expect(view.ibkrStatusKnown).toBe(false);
    expect(view.ibkrStatusError).toBe('HTTP 500');
    expect(banner(view)).toBe(false);
  });

  it('reads the venue, not the Gateway port label (ADR 020)', () => {
    expect(ibkrStatusView({ ...base, venue: 'live', mode: 'paper' as never }).deskVenue).toBe('live');
    expect(ibkrStatusView({ ...base, venue: undefined as never, mode: 'sim' as never }).deskVenue).toBe('sim');
    expect(ibkrStatusView({ ...base, venue: undefined as never }).deskVenue).toBeNull();
  });
});
