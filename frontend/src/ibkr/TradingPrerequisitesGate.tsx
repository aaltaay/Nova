/**
 * Trading prerequisites checklist.
 * ADR 021: while the API answers, the body is the desk diagnostics checklist
 * (`GET /api/diagnostics` -- which process, which .env, which fact failed);
 * the derived rows below stay as the fallback when the API itself is down.
 * Auto-covers the desk only when Nova API is down. Gateway-only mornings
 * stay usable -- click the header Gateway chip to open this panel.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useScannerBarProps } from '../components/scannerBarStore';
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL, DISCOVERY_PROVIDER_DEFAULT } from '../constants';
import { useWorkspace } from '../workspace/WorkspaceContext';
import {
  PREREQ_CLOSE_ARIA,
  PREREQ_CLOSE_LABEL,
  PREREQ_LEAD_API,
  PREREQ_LEAD_MANUAL,
} from './gatewayUxConstants';
import {
  buildTradingPrerequisites,
  gatewayPortMismatchHint,
} from './tradingPrerequisites';
import { usePrereqOverlayInputs } from './usePrereqOverlayInputs';
import { deskVenueOf, isPracticeDeskVenue } from './deskVenue';
import { PrereqItemRow } from './PrereqItemRow';
import { GatewayDoorTrail } from './GatewayDoorTrail';
import { refreshIbkrStatusNow, useIbkrStatus } from './useIbkrStatus';
import { TRADING_PREREQ_OPEN_EVENT } from './tradingPrereqUi';
import { launchIbGateway, type LaunchGatewayMode } from '../utils/launchIbGateway';
import type { DeskLaunchGatewayMode } from './GatewayModeLaunchButtons';
import { DiagnosticsChecklist } from './DiagnosticsChecklist';
import { fetchDiagnosticsBundle, useDiagnostics } from './useDiagnostics';
import { DIAG_UNREACHABLE } from '../constantGroups/diagnostics';
import { canReloadLocalBackend, startLocalApi } from '../utils/startLocalApi';
import './tradingPrerequisitesGate.css';

export function TradingPrerequisitesGate() {
  const bar = useScannerBarProps();
  const { ibkrConnected, ibkrGatewayMode } = useWorkspace();
  const ibkr = useIbkrStatus();
  const [launchBusyMode, setLaunchBusyMode] = useState<DeskLaunchGatewayMode | null>(null);
  const [reconnectBusy, setReconnectBusy] = useState(false);
  const [followBusy, setFollowBusy] = useState(false);
  const [freshLoginBusy, setFreshLoginBusy] = useState(false);
  const [launchHint, setLaunchHint] = useState<string | null>(null);
  const [reloadBusy, setReloadBusy] = useState(false);
  const [manualOpen, setManualOpen] = useState(false);
  const [autoDismissed, setAutoDismissed] = useState(false);
  const followTarget = gatewayPortMismatchHint(ibkr.disconnect_hint);

  const health = useMemo(() => bar?.health ?? { status: 'loading', latency_ms: 0 }, [bar?.health]);
  const discovery = bar?.discoveryProvider ?? DISCOVERY_PROVIDER_DEFAULT;
  const overlayGates = usePrereqOverlayInputs(health);

  const prereqs = useMemo(
    () =>
      buildTradingPrerequisites({
        health,
        ibkrEnabled: ibkr.enabled,
        ibkrConnected: Boolean((ibkrConnected || ibkr.connected) && !ibkr.stale),
        simMode: ibkr.mode === 'sim' || ibkr.sim === true,
        practiceOrders: isPracticeDeskVenue(deskVenueOf({ venue: ibkr.venue, mode: ibkr.mode })),
        ibkrTransportConnected: ibkr.transport_connected,
        preferredPortReachable: ibkr.preferred_port_reachable,
        disconnectHint: ibkr.disconnect_hint,
        sessionReason: ibkr.session_reason,
        sessionState: ibkr.session_state,
        secondFactorStale: ibkr.second_factor_stale,
        secondFactorAgeSec: ibkr.second_factor_age_sec,
        completedOrdersUnansweredSince: ibkr.completed_orders_unanswered_since,
        gatewayReadOnly: ibkr.gateway_read_only,
        apiFailStreak: overlayGates.apiFailStreak,
        deskActionInFlight: overlayGates.deskActionInFlight,
        sessionRecording: overlayGates.sessionRecording,
      }),
    [
      health,
      overlayGates.apiFailStreak,
      overlayGates.deskActionInFlight,
      overlayGates.sessionRecording,
      ibkr.enabled,
      ibkr.connected,
      ibkr.mode,
      ibkr.venue,
      ibkr.sim,
      ibkr.stale,
      ibkr.transport_connected,
      ibkr.preferred_port_reachable,
      ibkr.disconnect_hint,
      ibkr.session_reason,
      ibkr.session_state,
      ibkr.second_factor_stale,
      ibkr.second_factor_age_sec,
      ibkr.completed_orders_unanswered_since,
      ibkr.gateway_read_only,
      ibkrConnected,
    ],
  );

  const onLaunchGateway = useCallback(async (mode: DeskLaunchGatewayMode) => {
    if (launchBusyMode) return;
    setLaunchBusyMode(mode);
    setLaunchHint(null);
    const result = await launchIbGateway(mode);
    setLaunchHint(result.message);
    // "already_listening" can now come back as a backend-side session
    // rebuild (see routes/trading.py ibkr_launch_gateway) -- refresh
    // immediately instead of leaving the checklist stale for up to 5s.
    refreshIbkrStatusNow();
    setLaunchBusyMode(null);
  }, [launchBusyMode]);

  const onStartFreshLogin = useCallback(async () => {
    if (freshLoginBusy) return;
    setFreshLoginBusy(true);
    setLaunchHint(null);
    const mode: LaunchGatewayMode = ibkrGatewayMode === 'paper' ? 'paper' : 'live';
    const result = await launchIbGateway(mode, true);
    setLaunchHint(result.message);
    refreshIbkrStatusNow();
    setFreshLoginBusy(false);
  }, [freshLoginBusy, ibkrGatewayMode]);

  const onFollowGateway = useCallback(async () => {
    const target = gatewayPortMismatchHint(ibkr.disconnect_hint);
    if (!target || followBusy) return;
    setFollowBusy(true);
    setLaunchHint(null);
    try {
      const res = await novaFetch(`${API_BASE_URL}/api/ibkr/gateway-mode`, {
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
      const res = await novaFetch(`${API_BASE_URL}/api/ibkr/reconnect`, { method: 'POST' });
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

  const show = (prereqs.autoOverlay && !autoDismissed) || manualOpen;
  // Hooks stay above the early returns; the poll only runs while the panel is open.
  const diag = useDiagnostics(discovery === 'ibkr' && show);
  const onReloadBackend = useCallback(async () => {
    setReloadBusy(true);
    try {
      const result = await startLocalApi();
      if (!result.ok) setLaunchHint(result.error);
    } finally {
      setReloadBusy(false);
      await refreshIbkrStatusNow();
    }
  }, []);
  if (discovery !== 'ibkr') return null;
  if (!show) return null;

  const modeHint =
    ibkrGatewayMode === 'live'
      ? 'Target: LIVE Gateway port 4001'
      : ibkrGatewayMode === 'paper'
        ? 'Target: legacy IBKR paper Gateway port 4002 (set by hand -- not the Paper venue)'
        : 'Target: live Gateway API port 4001';

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
        {diag.data ? (
          <DiagnosticsChecklist
            data={diag.data}
            onRefresh={diag.refresh}
            copyBundle={fetchDiagnosticsBundle}
            busy={{ reconnect_ibkr: reconnectBusy, launch_gateway: launchBusyMode !== null, reload_backend: reloadBusy }}
            actions={{
              reconnect_ibkr: () => void onReconnectIbkr(),
              launch_gateway: () => void onLaunchGateway('live'),
              refresh: diag.refresh,
              ...(canReloadLocalBackend() ? { reload_backend: () => void onReloadBackend() } : {}),
            }}
          />
        ) : (
        <>
        {diag.error && (
          <p className="trading-prereq-gate__hint" data-testid="diag-unreachable">{DIAG_UNREACHABLE}</p>
        )}
        <ul className="trading-prereq-list">
          {prereqs.items.map((item) => (
            <PrereqItemRow
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
              onStartFreshLogin={() => void onStartFreshLogin()}
              freshLoginBusy={freshLoginBusy}
            />
          ))}
        </ul>
        </>
        )}
        {prereqs.warnings.map((warning) => (
          <div
            key={warning.id}
            className="trading-prereq-warning"
            role="status"
            data-testid={`trading-prereq-warning-${warning.id}`}
          >
            <span className="trading-prereq-warning__mark" aria-hidden>!</span>
            <div>
              <div className="trading-prereq-warning__label">{warning.label}</div>
              <div className="trading-prereq-warning__detail">{warning.detail}</div>
            </div>
          </div>
        ))}
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
