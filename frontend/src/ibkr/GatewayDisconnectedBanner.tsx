/**
 * Loud, unmissable "IB Gateway disconnected" banner — mounted once above the
 * scanner tabs so it is visible regardless of which tab (Dashboard/Gappers/
 * Gainers/Losers/After Hours) is active. Never silently omitted while
 * discovery=ibkr and Gateway is down (see ibkr-gateway-login-warning.mdc).
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
  ibkrConnected: boolean;
  ibkrGatewayMode?: 'paper' | 'live' | null;
}

export function GatewayDisconnectedBanner({
  discoveryProvider,
  ibkrConnected,
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

  if (discoveryProvider !== 'ibkr' || ibkrConnected) {
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
