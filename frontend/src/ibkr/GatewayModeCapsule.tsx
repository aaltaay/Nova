/**
 * Paper | Live segmented capsule. Persists IBKR_GATEWAY_MODE and reconnects.
 * Never sets IBKR_LIVE_TRADING_CONFIRMED -- live spend stays a separate gate.
 */
import { useState } from 'react';
import {
  API_BASE_URL,
  APP_DIALOG_SWITCH_LABEL,
  GATEWAY_MODE_API_RESTART_HINT,
  GLOBAL_BAR_MODE_LIVE,
  GLOBAL_BAR_MODE_PAPER,
  STOCK_VIEW_ACCOUNT_MODE_LIVE_TITLE,
  STOCK_VIEW_ACCOUNT_MODE_PAPER_TITLE,
} from '../constants';
import { confirmApp } from '../ux';
import { disconnectHintSwitchTarget } from './disconnectCopy';
import type { IbkrMode } from './types';
import { refreshIbkrStatusNow } from './useIbkrStatus';

interface GatewayModeResponse {
  ok: boolean;
  error?: string | null;
  detail?: string;
  mode?: IbkrMode;
}

export interface GatewayModeCapsuleProps {
  mode: IbkrMode;
  gatewayMode?: 'paper' | 'live';
  disconnectHint?: string | null;
  testId?: string;
  errorTestId?: string;
  className?: string;
}

function gatewayModeErrorMessage(
  res: Response,
  body: GatewayModeResponse,
  next: 'paper' | 'live',
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
): 'paper' | 'live' | null {
  if (gatewayMode === 'live' || gatewayMode === 'paper') return gatewayMode;
  if (mode === 'live' || mode === 'paper') return mode;
  return null;
}

export function GatewayModeCapsule({
  mode,
  gatewayMode,
  disconnectHint,
  testId = 'gateway-mode-capsule',
  errorTestId,
  className,
}: GatewayModeCapsuleProps) {
  const [pending, setPending] = useState<'paper' | 'live' | null>(null);
  const selected = pending ?? resolveCapsuleSelection(mode, gatewayMode);
  const [switching, setSwitching] = useState<'paper' | 'live' | null>(null);
  const [switchError, setSwitchError] = useState<string | null>(null);
  const hintTarget = disconnectHintSwitchTarget(disconnectHint);

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
      const res = await fetch(`${API_BASE_URL}/api/ibkr/gateway-mode`, {
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
          selected === 'paper' ? ' is-paper' : selected === 'live' ? ' is-live' : ''
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
      </div>
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
