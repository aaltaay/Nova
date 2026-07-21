/** Stock View header capsules — operator mode, Paper/Live.
 * The account-mode capsule intentionally switches which IBKR Gateway port
 * Nova targets (persist + reconnect); it never sets IBKR_LIVE_TRADING_CONFIRMED,
 * so live spend stays locked until armed separately. See ibkr/client.request_gateway_mode. */
import { useState } from 'react';
import {
  API_BASE_URL,
  APP_DIALOG_SWITCH_LABEL,
  GATEWAY_MODE_API_RESTART_HINT,
  STOCK_VIEW_ACCOUNT_MODE_LIVE,
  STOCK_VIEW_ACCOUNT_MODE_LIVE_TITLE,
  STOCK_VIEW_ACCOUNT_MODE_PAPER,
  STOCK_VIEW_ACCOUNT_MODE_PAPER_TITLE,
  STOCK_VIEW_OPERATOR_MODE_FULL_AUTO,
  STOCK_VIEW_OPERATOR_MODE_FULL_AUTO_TITLE,
  STOCK_VIEW_OPERATOR_MODE_MANUAL,
  STOCK_VIEW_OPERATOR_MODE_MANUAL_TITLE,
  STOCK_VIEW_OPERATOR_MODE_NORMAL,
  STOCK_VIEW_OPERATOR_MODE_NORMAL_TITLE,
} from '../constants';
import { disconnectHintSwitchTarget } from '../ibkr/disconnectCopy';
import { refreshIbkrStatusNow } from '../ibkr/useIbkrStatus';
import type { IbkrMode } from '../ibkr/types';
import { confirmApp } from '../ux';

interface GatewayModeResponse {
  ok: boolean;
  error?: string | null;
  detail?: string;
  mode?: IbkrMode;
}

export type StockViewOperatorMode = 'manual' | 'normal' | 'fully_automated';

/** Placeholder until Manual / Fully Automated are wired; Normal is the only live option. */
const OPERATOR_MODE: StockViewOperatorMode = 'normal';

export function StockViewOperatorModeCapsule() {
  return (
    <div
      className="sv-capsule sv-capsule--mode"
      role="group"
      aria-label="Operator mode"
      data-testid="sv-operator-mode-capsule"
    >
      <button
        type="button"
        className="sv-capsule__seg"
        disabled
        aria-pressed={OPERATOR_MODE === 'manual'}
        title={STOCK_VIEW_OPERATOR_MODE_MANUAL_TITLE}
      >
        {STOCK_VIEW_OPERATOR_MODE_MANUAL}
      </button>
      <button
        type="button"
        className={`sv-capsule__seg${OPERATOR_MODE === 'normal' ? ' is-selected' : ''}`}
        aria-pressed={OPERATOR_MODE === 'normal'}
        title={STOCK_VIEW_OPERATOR_MODE_NORMAL_TITLE}
      >
        {STOCK_VIEW_OPERATOR_MODE_NORMAL}
      </button>
      <button
        type="button"
        className="sv-capsule__seg"
        disabled
        aria-pressed={OPERATOR_MODE === 'fully_automated'}
        title={STOCK_VIEW_OPERATOR_MODE_FULL_AUTO_TITLE}
      >
        {STOCK_VIEW_OPERATOR_MODE_FULL_AUTO}
      </button>
    </div>
  );
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

interface AccountModeProps {
  /** Connected session mode from IBKR status (`disconnected` when not linked). */
  mode: IbkrMode;
  /**
   * Env target port (paper/live) — used for selection when disconnected so the
   * capsule still shows which Gateway Nova will dial, and stays clickable so
   * operators can switch onto the port that is actually listening.
   */
  gatewayMode?: 'paper' | 'live';
  /** From /api/ibkr/status — optional one-click switch target when mismatched. */
  disconnectHint?: string | null;
}

export function StockViewAccountModeCapsule({
  mode,
  gatewayMode,
  disconnectHint,
}: AccountModeProps) {
  const selected: 'paper' | 'live' | null =
    mode === 'live' || mode === 'paper'
      ? mode
      : gatewayMode === 'live' || gatewayMode === 'paper'
        ? gatewayMode
        : null;
  const [switching, setSwitching] = useState<'paper' | 'live' | null>(null);
  const [switchError, setSwitchError] = useState<string | null>(null);
  const hintTarget = disconnectHintSwitchTarget(disconnectHint);

  async function requestMode(next: 'paper' | 'live') {
    if (next === selected || switching) return;
    const message =
      next === 'live' ? STOCK_VIEW_ACCOUNT_MODE_LIVE_TITLE : STOCK_VIEW_ACCOUNT_MODE_PAPER_TITLE;
    const confirmed = await confirmApp({
      title: next === 'live' ? 'Switch to Live Gateway' : 'Switch to Paper Gateway',
      message,
      confirmLabel: APP_DIALOG_SWITCH_LABEL,
      tone: next === 'live' ? 'danger' : 'warning',
    });
    if (!confirmed) return;

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
      refreshIbkrStatusNow();
    }
  }

  return (
    <div className="sv-capsule-wrap">
      <div
        className="sv-capsule sv-capsule--account"
        role="group"
        aria-label="Account mode"
        data-testid="sv-account-mode-capsule"
      >
        <button
          type="button"
          className={`sv-capsule__seg${selected === 'paper' ? ' is-selected is-paper' : ''}`}
          aria-pressed={selected === 'paper'}
          disabled={switching !== null}
          title={STOCK_VIEW_ACCOUNT_MODE_PAPER_TITLE}
          onClick={() => requestMode('paper')}
        >
          {switching === 'paper' ? '…' : STOCK_VIEW_ACCOUNT_MODE_PAPER}
        </button>
        <button
          type="button"
          className={`sv-capsule__seg${selected === 'live' ? ' is-selected is-live' : ''}`}
          aria-pressed={selected === 'live'}
          disabled={switching !== null}
          title={STOCK_VIEW_ACCOUNT_MODE_LIVE_TITLE}
          onClick={() => requestMode('live')}
        >
          {switching === 'live' ? '…' : STOCK_VIEW_ACCOUNT_MODE_LIVE}
        </button>
      </div>
      {hintTarget && mode === 'disconnected' && !switchError && (
        <button
          type="button"
          className="sv-capsule__hint-cta"
          data-testid="sv-disconnect-hint-cta"
          disabled={switching !== null}
          onClick={() => requestMode(hintTarget)}
        >
          Switch to {hintTarget === 'live' ? 'Live' : 'Paper'}
        </button>
      )}
      {switchError && (
        <span className="sv-capsule__error" role="alert" data-testid="sv-account-mode-error">
          {switchError}
        </span>
      )}
    </div>
  );
}
