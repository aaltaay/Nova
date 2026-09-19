/** One Trading prerequisites checklist row + its CTA (split out of the gate for the 400-line limit). */
import { BackendStartButton } from '../components/BackendStartButton';
import {
  PREREQ_GATEWAY_FOLLOW_CTA_BUSY_LABEL,
  PREREQ_GATEWAY_FOLLOW_LIVE_CTA_LABEL,
  PREREQ_GATEWAY_FOLLOW_PAPER_CTA_LABEL,
  PREREQ_GATEWAY_RECONNECT_CTA_BUSY_LABEL,
  PREREQ_GATEWAY_RECONNECT_CTA_LABEL,
  PREREQ_GATEWAY_STALE_SECOND_FACTOR_CTA_BUSY_LABEL,
  PREREQ_GATEWAY_STALE_SECOND_FACTOR_CTA_LABEL,
} from './gatewayUxConstants';
import { GatewayModeLaunchButtons } from './GatewayModeLaunchButtons';
import type { PrereqItem } from './tradingPrerequisites';
import type { LaunchGatewayMode } from '../utils/launchIbGateway';

export function PrereqItemRow({
  item,
  onLaunchGateway,
  launchBusyMode,
  onReconnectIbkr,
  onFollowGateway,
  followTarget,
  reconnectBusy,
  followBusy,
  healthFlag,
  healthHint,
  onApiStarted,
  onStartFreshLogin,
  freshLoginBusy,
}: {
  item: PrereqItem;
  onLaunchGateway: (mode: LaunchGatewayMode) => void;
  launchBusyMode: LaunchGatewayMode | null;
  onReconnectIbkr: () => void;
  onFollowGateway: () => void;
  followTarget: 'paper' | 'live' | null;
  reconnectBusy: boolean;
  followBusy: boolean;
  healthFlag?: string;
  healthHint?: string;
  onApiStarted?: () => void;
  onStartFreshLogin: () => void;
  freshLoginBusy: boolean;
}) {
  return (
    <li
      className={`trading-prereq-item${item.ok ? ' trading-prereq-item--ok' : ' trading-prereq-item--bad'}`}
      data-testid={`trading-prereq-${item.id}`}
    >
      <span className="trading-prereq-item__mark" aria-hidden>
        {item.ok ? 'OK' : '!'}
      </span>
      <div className="trading-prereq-item__body">
        <div className="trading-prereq-item__label">{item.label}</div>
        <div className="trading-prereq-item__detail">{item.detail}</div>
        {!item.ok && item.action === 'start_api' && (
          <div className="trading-prereq-item__cta">
            <BackendStartButton
              flag={healthFlag}
              flagHint={healthHint}
              onStarted={onApiStarted}
            />
          </div>
        )}
        {!item.ok && item.action === 'launch_gateway' && (
          <div className="trading-prereq-item__cta">
            <GatewayModeLaunchButtons
              busyMode={launchBusyMode}
              onLaunch={onLaunchGateway}
            />
          </div>
        )}
        {!item.ok && item.action === 'switch_gateway_mode' && followTarget && (
          <div className="trading-prereq-item__cta">
            <button
              type="button"
              className="trading-prereq-cta"
              onClick={onFollowGateway}
              disabled={followBusy}
              data-testid="trading-prereq-follow-gateway"
            >
              {followBusy
                ? PREREQ_GATEWAY_FOLLOW_CTA_BUSY_LABEL
                : followTarget === 'paper'
                  ? PREREQ_GATEWAY_FOLLOW_PAPER_CTA_LABEL
                  : PREREQ_GATEWAY_FOLLOW_LIVE_CTA_LABEL}
            </button>
          </div>
        )}
        {!item.ok && item.action === 'stale_second_factor' && (
          <div className="trading-prereq-item__cta">
            <button
              type="button"
              className="trading-prereq-cta"
              onClick={onStartFreshLogin}
              disabled={freshLoginBusy}
              data-testid="trading-prereq-fresh-login"
            >
              {freshLoginBusy
                ? PREREQ_GATEWAY_STALE_SECOND_FACTOR_CTA_BUSY_LABEL
                : PREREQ_GATEWAY_STALE_SECOND_FACTOR_CTA_LABEL}
            </button>
          </div>
        )}
        {!item.ok && item.action === 'reconnect_ibkr' && (
          <div className="trading-prereq-item__cta">
            <button
              type="button"
              className="trading-prereq-cta"
              onClick={onReconnectIbkr}
              disabled={reconnectBusy}
              data-testid="trading-prereq-reconnect"
            >
              {reconnectBusy
                ? PREREQ_GATEWAY_RECONNECT_CTA_BUSY_LABEL
                : PREREQ_GATEWAY_RECONNECT_CTA_LABEL}
            </button>
          </div>
        )}
        {!item.ok && item.action === 'env_ibkr' && (
          <div className="trading-prereq-item__cta trading-prereq-item__cta--hint">
            Edit local <code>.env</code> (desktop: <code>%APPDATA%\Nova\.env</code>), then restart Nova.
          </div>
        )}
      </div>
    </li>
  );
}
