/**
 * Side-by-side Open paper / Open live Gateway launchers.
 */
import {
  GATEWAY_BANNER_CTA_BUSY_LABEL,
  PREREQ_OPEN_LIVE_LABEL,
  PREREQ_OPEN_PAPER_LABEL,
} from './gatewayUxConstants';
import './gatewayModeLaunchButtons.css';

type GatewayMode = 'paper' | 'live';

interface Props {
  busyMode: GatewayMode | null;
  onLaunch: (mode: GatewayMode) => void;
  paperTestId?: string;
  liveTestId?: string;
}

export function GatewayModeLaunchButtons({
  busyMode,
  onLaunch,
  paperTestId = 'open-gateway-paper',
  liveTestId = 'open-gateway-live',
}: Props) {
  const busy = busyMode != null;
  return (
    <div className="gateway-mode-launch-row">
      <button
        type="button"
        className="trading-prereq-cta trading-prereq-cta--paper"
        data-testid={paperTestId}
        disabled={busy}
        onClick={() => onLaunch('paper')}
      >
        {busyMode === 'paper' ? GATEWAY_BANNER_CTA_BUSY_LABEL : PREREQ_OPEN_PAPER_LABEL}
      </button>
      <button
        type="button"
        className="trading-prereq-cta trading-prereq-cta--live"
        data-testid={liveTestId}
        disabled={busy}
        onClick={() => onLaunch('live')}
      >
        {busyMode === 'live' ? GATEWAY_BANNER_CTA_BUSY_LABEL : PREREQ_OPEN_LIVE_LABEL}
      </button>
    </div>
  );
}
