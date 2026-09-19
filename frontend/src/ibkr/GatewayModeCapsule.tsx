/**
 * Paper | Live | Sim segmented capsule.
 * Paper/Live persist IBKR_GATEWAY_MODE and reconnect.
 * Sim POSTs /api/sim and never places to Gateway.
 * Never sets IBKR_LIVE_TRADING_CONFIRMED -- live spend stays a separate gate.
 */
import { useState } from 'react';
import { novaFetch } from '../api/novaFetch';
import {
  API_BASE_URL,
  APP_DIALOG_SWITCH_LABEL,
  GATEWAY_MODE_API_RESTART_HINT,
  GLOBAL_BAR_MODE_LIVE,
  GLOBAL_BAR_MODE_PAPER,
  GLOBAL_BAR_MODE_SIM,
  GLOBAL_BAR_MODE_CAPTURE,
  SIM_PRACTICE_FLAG_TEXT,
  STOCK_VIEW_ACCOUNT_MODE_LIVE_TITLE,
  STOCK_VIEW_ACCOUNT_MODE_PAPER_TITLE,
  STOCK_VIEW_ACCOUNT_MODE_SIM_TITLE,
} from '../constants';
import { confirmApp } from '../ux';
import { disconnectHintSwitchTarget } from './disconnectCopy';
import type { IbkrMode } from './types';
import { refreshIbkrStatusNow } from './useIbkrStatus';

interface GatewayModeResponse {
  ok?: boolean;
  error?: string | null;
  detail?: string;
  mode?: IbkrMode;
  launch_action?: string | null;
  message?: string | null;
  sim?: boolean;
}

export type CapsuleSelection = 'paper' | 'live' | 'sim' | 'capture';

export interface GatewayModeCapsuleProps {
  mode: IbkrMode;
  gatewayMode?: 'paper' | 'live';
  accountKind?: string | null;
  intentionalMode?: 'paper' | 'live' | null;
  disconnectHint?: string | null;
  testId?: string;
  errorTestId?: string;
  className?: string;
}

function gatewayModeErrorMessage(
  res: Response,
  body: GatewayModeResponse,
  next: CapsuleSelection,
): string {
  if (res.status === 404) {
    return GATEWAY_MODE_API_RESTART_HINT;
  }
  const detail = typeof body.detail === 'string' ? body.detail : '';
  if (detail && (res.status === 404 || detail.toLowerCase().includes('not found'))) {
    return GATEWAY_MODE_API_RESTART_HINT;
  }
  return body.error || detail || `Switch to ${next} failed`;
}

export function resolveCapsuleSelection(
  mode: IbkrMode,
  gatewayMode?: 'paper' | 'live',
  accountKind?: string | null,
  intentional?: 'paper' | 'live' | null,
): CapsuleSelection | null {
  if (mode === 'sim') return 'sim';
  if (mode === 'capture') return 'capture';
  if (intentional === 'paper' || intentional === 'live') return intentional;
  if (accountKind === 'paper' || accountKind === 'live') return accountKind;
  if (gatewayMode === 'live' || gatewayMode === 'paper') return gatewayMode;
  if (mode === 'live' || mode === 'paper') return mode;
  return null;
}

export function GatewayModeCapsule({
  mode,
  gatewayMode,
  accountKind = null,
  intentionalMode = null,
  disconnectHint,
  testId = 'gateway-mode-capsule',
  errorTestId,
  className,
}: GatewayModeCapsuleProps) {
  const [pending, setPending] = useState<CapsuleSelection | null>(null);
  const selected =
    pending ?? resolveCapsuleSelection(mode, gatewayMode, accountKind, intentionalMode);
  const [switching, setSwitching] = useState<CapsuleSelection | null>(null);
  const [switchError, setSwitchError] = useState<string | null>(null);
  const hintTarget = disconnectHintSwitchTarget(disconnectHint);

  async function requestSim() {
    if (selected === 'sim' || switching) return;
    const confirmed = await confirmApp({
      title: 'Switch to Sim practice',
      message: STOCK_VIEW_ACCOUNT_MODE_SIM_TITLE,
      confirmLabel: APP_DIALOG_SWITCH_LABEL,
      tone: 'warning',
    });
    if (!confirmed) return;
    setPending('sim');
    setSwitching('sim');
    setSwitchError(null);
    try {
      const res = await novaFetch(`${API_BASE_URL}/api/sim`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: true }),
      });
      const body: GatewayModeResponse = await res.json().catch(() => ({
        ok: false,
        error: `Switch to Sim failed`,
      }));
      if (!res.ok || body.sim !== true) {
        setSwitchError(gatewayModeErrorMessage(res, body, 'sim'));
      }
    } catch {
      setSwitchError('Could not reach Nova backend to switch to Sim');
    } finally {
      setSwitching(null);
      setPending(null);
      refreshIbkrStatusNow();
    }
  }

  
  async function requestCapture() {
    if (selected === 'capture' || switching) return;
    const confirmed = await confirmApp({
      title: 'Switch to Capture',
      message:
        'CAPTURE records IBKR tape/L2/quotes/bars for Monday Sim replay. Places are blocked. Keep Trader/scanner light.',
      confirmLabel: APP_DIALOG_SWITCH_LABEL,
      tone: 'warning',
    });
    if (!confirmed) return;
    setPending('capture');
    setSwitching('capture');
    setSwitchError(null);
    try {
      if (selected === 'sim' || mode === 'sim') {
        await novaFetch(`${API_BASE_URL}/api/sim`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ enabled: false }),
        });
      }
      const res = await novaFetch(`${API_BASE_URL}/api/capture`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: true }),
      });
      const body = await res.json().catch(() => ({ capture: false }));
      if (!res.ok || body.capture !== true) {
        setSwitchError(
          (typeof body.detail === 'string' && body.detail) ||
            body.error ||
            'Switch to Capture failed',
        );
      }
    } catch {
      setSwitchError('Could not reach Nova backend to switch to Capture');
    } finally {
      setSwitching(null);
      setPending(null);
      refreshIbkrStatusNow();
    }
  }

  async function requestMode(next: 'paper' | 'live') {
    if (next === selected || switching) return;
    const confirmed = await confirmApp({
      title: next === 'live' ? 'Switch to Live Gateway' : 'Switch to Paper Gateway',
      message:
        next === 'live' ? STOCK_VIEW_ACCOUNT_MODE_LIVE_TITLE : STOCK_VIEW_ACCOUNT_MODE_PAPER_TITLE,
      confirmLabel: APP_DIALOG_SWITCH_LABEL,
      tone: next === 'live' ? 'danger' : 'warning',
    });
    if (!confirmed) return;

    setPending(next);
    setSwitching(next);
    setSwitchError(null);
    try {
      if (selected === 'sim' || mode === 'sim') {
        const simRes = await novaFetch(`${API_BASE_URL}/api/sim`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ enabled: false }),
        });
        if (!simRes.ok) {
          const simBody: GatewayModeResponse = await simRes.json().catch(() => ({}));
          setSwitchError(gatewayModeErrorMessage(simRes, simBody, next));
          return;
        }
      }
      const res = await novaFetch(`${API_BASE_URL}/api/ibkr/gateway-mode`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: next }),
      });
      const body: GatewayModeResponse = await res.json().catch(() => ({
        ok: false,
        error: res.status === 404 ? GATEWAY_MODE_API_RESTART_HINT : `Switch to ${next} failed`,
      }));
      if (!res.ok || !body.ok) {
        setSwitchError(gatewayModeErrorMessage(res, body, next));
      } else if (body.message && body.launch_action && body.launch_action !== 'noop') {
        setSwitchError(body.message);
      }
    } catch {
      setSwitchError('Could not reach Nova backend to switch Gateway mode');
    } finally {
      setSwitching(null);
      setPending(null);
      refreshIbkrStatusNow();
    }
  }

  return (
    <div className={`gw-mode-capsule-wrap${className ? ` ${className}` : ''}`}>
      <div
        className={`gw-mode-capsule sv-capsule${
          selected === 'paper'
            ? ' is-paper'
            : selected === 'live'
              ? ' is-live'
              : selected === 'sim' ? ' is-sim' : selected === 'capture' ? ' is-capture' : ''
        }`}
        role="group"
        aria-label="Account mode"
        data-testid={testId}
      >
        <button
          type="button"
          className={`gw-mode-capsule__seg sv-capsule__seg${
            selected === 'paper' ? ' is-selected is-paper' : ''
          }`}
          aria-pressed={selected === 'paper'}
          disabled={switching !== null}
          title={STOCK_VIEW_ACCOUNT_MODE_PAPER_TITLE}
          onClick={() => requestMode('paper')}
        >
          {switching === 'paper' ? '…' : GLOBAL_BAR_MODE_PAPER}
        </button>
        <button
          type="button"
          className={`gw-mode-capsule__seg sv-capsule__seg${
            selected === 'live' ? ' is-selected is-live' : ''
          }`}
          aria-pressed={selected === 'live'}
          disabled={switching !== null}
          title={STOCK_VIEW_ACCOUNT_MODE_LIVE_TITLE}
          onClick={() => requestMode('live')}
        >
          {switching === 'live' ? '…' : GLOBAL_BAR_MODE_LIVE}
        </button>
        <button
          type="button"
          className={`gw-mode-capsule__seg sv-capsule__seg${
            selected === 'sim' ? ' is-selected is-sim' : ''
          }`}
          aria-pressed={selected === 'sim'}
          disabled={switching !== null}
          title={STOCK_VIEW_ACCOUNT_MODE_SIM_TITLE}
          data-testid={`${testId}-sim`}
          onClick={() => requestSim()}
        >
          {switching === 'sim' ? '…' : GLOBAL_BAR_MODE_SIM}
        </button>
        <button
          type="button"
          className={`gw-mode-capsule__seg sv-capsule__seg${
            selected === 'capture' ? ' is-selected is-capture' : ''
          }`}
          aria-pressed={selected === 'capture'}
          disabled={switching !== null}
          title="Capture IBKR session for Sim replay — places blocked"
          data-testid={`${testId}-capture`}
          onClick={() => requestCapture()}
        >
          {switching === 'capture' ? '…' : GLOBAL_BAR_MODE_CAPTURE}
        </button>
      </div>
      {selected === 'sim' && (
        <span className="gw-mode-capsule__sim-flag" data-testid="sim-practice-flag">
          {SIM_PRACTICE_FLAG_TEXT}
        </span>
      )}
      {hintTarget && mode === 'disconnected' && !switchError && (
        <button
          type="button"
          className="gw-mode-capsule__hint-cta"
          data-testid="sv-disconnect-hint-cta"
          disabled={switching !== null}
          onClick={() => requestMode(hintTarget)}
        >
          Switch to {hintTarget === 'live' ? GLOBAL_BAR_MODE_LIVE : GLOBAL_BAR_MODE_PAPER}
        </button>
      )}
      {switchError && (
        <span
          className="gw-mode-capsule__error sv-capsule__error"
          role="alert"
          data-testid={errorTestId ?? `${testId}-error`}
        >
          {switchError}
        </span>
      )}
    </div>
  );
}
