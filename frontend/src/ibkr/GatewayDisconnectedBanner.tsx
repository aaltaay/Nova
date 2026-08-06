/**
 * Loud, unmissable "IB Gateway disconnected" banner -- mounted once above the
 * scanner tabs so it is visible regardless of which tab (Dashboard/Gappers/
 * Gainers/Losers/After Hours) is active. Never silently omitted while
 * discovery=ibkr and Gateway is down (see ibkr-gateway-login-warning.mdc).
 *
 * Gate: login CTA only when Gateway transport is actually down (or both API
 * ports dark / disconnect login hint). Do NOT show for Error 1100-style
 * transport_up + session !usable -- reconnect recovers that without a login.
 */
import { useCallback, useState } from 'react';
import { HEADER_GATEWAY_LAUNCH_HINT } from '../constants';
import { launchIbGateway } from '../utils/launchIbGateway';
import { emptyIbkrDisconnectedMessage } from './disconnectCopy';
import {
  GATEWAY_BANNER_CTA_BUSY_LABEL,
  GATEWAY_BANNER_CTA_LABEL,
  GATEWAY_BANNER_TITLE,
} from './gatewayUxConstants';

interface Props {
  discoveryProvider: string;
  /** Product usable (status.connected). Kept for callers / tests. */
  ibkrConnected: boolean;
  /** Raw socket -- when true, suppress login CTA even if !usable. */
  ibkrTransportConnected?: boolean;
  /** Both preferred + alternate Gateway API ports unreachable. */
  ibkrPortsDark?: boolean;
  /** Port / login disconnect_hint from status (e.g. both_ports_unreachable). */
  ibkrDisconnectHint?: string | null;
  ibkrGatewayMode?: 'paper' | 'live' | null;
}

/** True when the loud login banner should render (Gateway actually down). */
export function shouldShowGatewayLoginBanner(props: {
  discoveryProvider: string;
  ibkrConnected: boolean;
  ibkrTransportConnected?: boolean;
  ibkrPortsDark?: boolean;
  ibkrDisconnectHint?: string | null;
}): boolean {
  if (props.discoveryProvider !== 'ibkr') return false;
  if (props.ibkrConnected) return false;
  // Soft blip / syncing: socket still up -- reconnect owns recovery (no login CTA).
  if (props.ibkrTransportConnected === true) return false;

  const hint = props.ibkrDisconnectHint ?? null;
  const loginHint =
    hint === 'both_ports_unreachable'
    || hint === 'paper_port_open_but_disconnected'
    || hint === 'live_port_open_but_disconnected'
    || hint === 'paper_port_refused_live_listening'
    || hint === 'live_port_refused_paper_listening';

  // Explicit transport-down, ports dark, or a disconnect/login hint.
  if (props.ibkrTransportConnected === false) return true;
  if (props.ibkrPortsDark === true) return true;
  if (loginHint) return true;

  // Legacy status without transport_connected: fall back to !usable.
  if (props.ibkrTransportConnected === undefined) return true;
  return false;
}

export function GatewayDisconnectedBanner({
  discoveryProvider,
  ibkrConnected,
  ibkrTransportConnected,
  ibkrPortsDark = false,
  ibkrDisconnectHint = null,
  ibkrGatewayMode = null,
}: Props) {
  const [busy, setBusy] = useState(false);
  const [launchHint, setLaunchHint] = useState<string | null>(null);

  const onOpenGateway = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    setLaunchHint(null);
    const result = await launchIbGateway();
    setLaunchHint(result.message);
    setBusy(false);
  }, [busy]);

  if (
    !shouldShowGatewayLoginBanner({
      discoveryProvider,
      ibkrConnected,
      ibkrTransportConnected,
      ibkrPortsDark,
      ibkrDisconnectHint,
    })
  ) {
    return null;
  }

  return (
    <div
      className="gateway-disconnected-banner"
      role="alert"
      aria-live="assertive"
      data-testid="gateway-disconnected-banner"
    >
      <strong className="gateway-disconnected-banner__title">{GATEWAY_BANNER_TITLE}</strong>
      <div className="gateway-disconnected-banner__body">
        {emptyIbkrDisconnectedMessage(ibkrGatewayMode)}
      </div>
      <div className="gateway-disconnected-banner__actions">
        <button
          type="button"
          className="gateway-disconnected-banner__cta"
          onClick={() => void onOpenGateway()}
          disabled={busy}
        >
          {busy ? GATEWAY_BANNER_CTA_BUSY_LABEL : GATEWAY_BANNER_CTA_LABEL}
        </button>
        <span className="gateway-disconnected-banner__hint">
          {launchHint || HEADER_GATEWAY_LAUNCH_HINT}
        </span>
      </div>
    </div>
  );
}
