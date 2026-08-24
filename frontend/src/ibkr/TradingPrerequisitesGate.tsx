/**
 * Trading prerequisites checklist.
 * Auto-covers the desk only when Nova API is down. Gateway-only mornings
 * stay usable -- click the header Gateway chip to open this panel.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { BackendStartButton } from '../components/BackendStartButton';
import { useScannerBarProps } from '../components/scannerBarStore';
import { API_BASE_URL, DISCOVERY_PROVIDER_DEFAULT } from '../constants';
import { useWorkspace } from '../workspace/WorkspaceContext';
import {
  PREREQ_CLOSE_ARIA,
  PREREQ_CLOSE_LABEL,
  PREREQ_GATEWAY_FOLLOW_CTA_BUSY_LABEL,
  PREREQ_LEAD_API,
  PREREQ_LEAD_MANUAL,
  PREREQ_GATEWAY_FOLLOW_LIVE_CTA_LABEL,
  PREREQ_GATEWAY_FOLLOW_PAPER_CTA_LABEL,
  PREREQ_GATEWAY_RECONNECT_CTA_BUSY_LABEL,
  PREREQ_GATEWAY_RECONNECT_CTA_LABEL,
} from './gatewayUxConstants';
import {
  buildTradingPrerequisites,
  gatewayPortMismatchHint,
  type PrereqItem,
} from './tradingPrerequisites';
import { GatewayModeLaunchButtons } from './GatewayModeLaunchButtons';
import { GatewayDoorTrail } from './GatewayDoorTrail';
import { refreshIbkrStatusNow, useIbkrStatus } from './useIbkrStatus';
import { TRADING_PREREQ_OPEN_EVENT } from './tradingPrereqUi';
import { launchIbGateway, type LaunchGatewayMode } from '../utils/launchIbGateway';
import './tradingPrerequisitesGate.css';

function ItemRow({
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

export function TradingPrerequisitesGate() {
  const bar = useScannerBarProps();
  const { ibkrConnected, ibkrGatewayMode } = useWorkspace();
  const ibkr = useIbkrStatus();
  const [launchBusyMode, setLaunchBusyMode] = useState<LaunchGatewayMode | null>(null);
  const [reconnectBusy, setReconnectBusy] = useState(false);
  const [followBusy, setFollowBusy] = useState(false);
  const [launchHint, setLaunchHint] = useState<string | null>(null);
  const [manualOpen, setManualOpen] = useState(false);
  const [autoDismissed, setAutoDismissed] = useState(false);
  const followTarget = gatewayPortMismatchHint(ibkr.disconnect_hint);

  const health = bar?.health ?? { status: 'loading', latency_ms: 0 };
  const discovery = bar?.discoveryProvider ?? DISCOVERY_PROVIDER_DEFAULT;

  const prereqs = useMemo(
    () =>
      buildTradingPrerequisites({
        health,
        ibkrEnabled: ibkr.enabled,
        ibkrConnected: Boolean(ibkrConnected || ibkr.connected),
        ibkrTransportConnected: ibkr.transport_connected,
        preferredPortReachable: ibkr.preferred_port_reachable,
        disconnectHint: ibkr.disconnect_hint,
        sessionReason: ibkr.session_reason,
      }),
    [
      health,
      ibkr.enabled,
      ibkr.connected,
      ibkr.transport_connected,
      ibkr.preferred_port_reachable,
      ibkr.disconnect_hint,
      ibkr.session_reason,
      ibkrConnected,
    ],
  );

  const onLaunchGateway = useCallback(async (mode: LaunchGatewayMode) => {
    if (launchBusyMode) return;
    setLaunchBusyMode(mode);
    setLaunchHint(null);
    const result = await launchIbGateway(mode);
    setLaunchHint(result.message);
    setLaunchBusyMode(null);
  }, [launchBusyMode]);

  const onFollowGateway = useCallback(async () => {
    const target = gatewayPortMismatchHint(ibkr.disconnect_hint);
    if (!target || followBusy) return;
    setFollowBusy(true);
    setLaunchHint(null);
    try {
      const res = await fetch(`${API_BASE_URL}/api/ibkr/gateway-mode`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: target }),
      });
      const body = (await res.json().catch(() => ({}))) as {
        ok?: boolean;
        error?: string;
        connected?: boolean;
      };
      refreshIbkrStatusNow();
      if (res.ok && body.ok !== false && body.connected) {
        setLaunchHint(`Attached to ${target} Gateway.`);
      } else {
        setLaunchHint(body.error || `Could not switch to ${target} Gateway.`);
      }
    } catch {
      setLaunchHint('Switch request failed -- Nova API may be down.');
    } finally {
      setFollowBusy(false);
    }
  }, [followBusy, ibkr.disconnect_hint]);

  const onReconnectIbkr = useCallback(async () => {
    if (reconnectBusy) return;
    setReconnectBusy(true);
    setLaunchHint(null);
    try {
      const res = await fetch(`${API_BASE_URL}/api/ibkr/reconnect`, { method: 'POST' });
      const body = (await res.json().catch(() => ({}))) as {
        connected?: boolean;
        session_reason?: string;
        session_state?: string;
      };
      refreshIbkrStatusNow();
      if (res.ok && body.connected) {
        setLaunchHint('Nova session READY again.');
      } else if (res.ok) {
        setLaunchHint(
          `Reconnect finished but session not READY yet (${body.session_state || 'unknown'}`
            + `${body.session_reason ? `: ${body.session_reason}` : ''}). `
            + 'If it stays red, restart Nova API.',
        );
      } else {
        setLaunchHint('Reconnect request failed -- check Nova API logs, or restart the API.');
      }
    } catch {
      setLaunchHint('Reconnect request failed -- Nova API may be down.');
    } finally {
      setReconnectBusy(false);
    }
  }, [reconnectBusy]);

  // Auto-heal Start API is owned by BackendStartButton on API_DOWN only.
  useEffect(() => {
    if (prereqs.deskReady) setLaunchHint(null);
  }, [prereqs.deskReady]);

  useEffect(() => {
    if (!prereqs.autoOverlay) setAutoDismissed(false);
  }, [prereqs.autoOverlay]);

  useEffect(() => {
    const open = () => {
      setManualOpen(true);
      setAutoDismissed(false);
    };
    window.addEventListener(TRADING_PREREQ_OPEN_EVENT, open);
    return () => window.removeEventListener(TRADING_PREREQ_OPEN_EVENT, open);
  }, []);

  const closePanel = useCallback(() => {
    setManualOpen(false);
    setAutoDismissed(true);
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closePanel();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [closePanel]);

  if (discovery !== 'ibkr') return null;
  const show = (prereqs.autoOverlay && !autoDismissed) || manualOpen;
  if (!show) return null;

  const modeHint =
    ibkrGatewayMode === 'live'
      ? 'Target: LIVE Gateway port 4001'
      : ibkrGatewayMode === 'paper'
        ? 'Target: PAPER Gateway port 4002'
        : 'Target: IB Gateway API port (4001 live / 4002 paper)';

  return (
    <div
      className="trading-prereq-gate"
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="trading-prereq-title"
      data-testid="trading-prerequisites-gate"
      onClick={closePanel}
    >
      <div
        className="trading-prereq-gate__panel"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="trading-prereq-gate__head">
          <h2 id="trading-prereq-title" className="trading-prereq-gate__title">
            Trading prerequisites
          </h2>
          <button
            type="button"
            className="trading-prereq-gate__close"
            data-testid="trading-prereq-close"
            aria-label={PREREQ_CLOSE_ARIA}
            onClick={closePanel}
          >
            {PREREQ_CLOSE_LABEL}
          </button>
        </div>
        <p className="trading-prereq-gate__lead">
          {prereqs.autoOverlay ? PREREQ_LEAD_API : PREREQ_LEAD_MANUAL}
        </p>
        <p className="trading-prereq-gate__mode">{modeHint}</p>
        <ul className="trading-prereq-list">
          {prereqs.items.map((item) => (
            <ItemRow
              key={item.id}
              item={item}
              onLaunchGateway={(mode) => void onLaunchGateway(mode)}
              launchBusyMode={launchBusyMode}
              onReconnectIbkr={() => void onReconnectIbkr()}
              onFollowGateway={() => void onFollowGateway()}
              followTarget={followTarget}
              reconnectBusy={reconnectBusy}
              followBusy={followBusy}
              healthFlag={health.flag}
              healthHint={health.flag_hint}
            />
          ))}
        </ul>
        {launchHint && (
          <p className="trading-prereq-gate__hint" data-testid="trading-prereq-launch-hint">
            {launchHint}
          </p>
        )}
        <GatewayDoorTrail compact />
      </div>
    </div>
  );
}
