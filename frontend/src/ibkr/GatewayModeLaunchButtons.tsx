/**
 * The live Gateway launcher. Live is the feed for every venue (ADR 020); the
 * IBKR paper Gateway (4002) is legacy with no desk button -- by hand only via
 * `POST /api/ibkr/gateway-mode {"mode":"paper"}` -- and is never offered as a
 * fallback (beside a live login it is read-only and carries no tape).
 */
import {
  GATEWAY_BANNER_CTA_BUSY_LABEL,
  GATEWAY_WHY_LAUNCHING,
  PREREQ_OPEN_LIVE_LABEL,
  PREREQ_OPEN_LIVE_TITLE,
} from './gatewayUxConstants';
import './gatewayModeLaunchButtons.css';

/** The only Gateway a desk button may launch. */
export type DeskLaunchGatewayMode = 'live';

interface Props {
  busyMode: DeskLaunchGatewayMode | null;
  onLaunch: (mode: DeskLaunchGatewayMode) => void;
  liveTestId?: string;
}

export function GatewayModeLaunchButtons({
  busyMode,
  onLaunch,
  liveTestId = 'open-gateway-live',
}: Props) {
  const busy = busyMode != null;
  return (
    <div className="gateway-mode-launch-row">
      <button
        type="button"
        className="trading-prereq-cta trading-prereq-cta--live"
        data-testid={liveTestId}
        title={busy ? undefined : PREREQ_OPEN_LIVE_TITLE}
        disabled={busy}
        data-why={busy ? GATEWAY_WHY_LAUNCHING : undefined}
        onClick={() => onLaunch('live')}
      >
        {busyMode === 'live' ? GATEWAY_BANNER_CTA_BUSY_LABEL : PREREQ_OPEN_LIVE_LABEL}
      </button>
    </div>
  );
}
