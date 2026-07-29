/**
 * Restart the local Nova API while the dashboard is connected — dev / desktop only.
 * Uses the same kill+restart path as BackendStartButton (Start-NovaApi.ps1 / Electron sidecar).
 */
import { useState } from 'react';
import {
  BACKEND_RELOAD_BUTTON_LABEL,
  BACKEND_RELOAD_BUTTON_TITLE,
  BACKEND_RELOAD_CONFIRM_MESSAGE,
  BACKEND_RELOAD_CONFIRM_TITLE,
} from '../constants';
import { confirmApp } from '../ux';
import { startLocalApi } from '../utils/startLocalApi';

interface Props {
  /** Called after a successful restart so scanner/health can refresh. */
  onReloaded?: () => void;
}

export function BackendReloadButton({ onReloaded }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  async function handleClick() {
    if (busy) return;
    const ok = await confirmApp({
      title: BACKEND_RELOAD_CONFIRM_TITLE,
      message: BACKEND_RELOAD_CONFIRM_MESSAGE,
      confirmLabel: 'Reload',
      tone: 'warning',
    });
    if (!ok) return;

    setBusy(true);
    setError(null);
    setNote('Restarting API…');
    const result = await startLocalApi();
    setBusy(false);
    if (!result.ok) {
      setNote(null);
      setError(result.error);
      return;
    }
    setNote('Backend reloaded');
    onReloaded?.();
    window.setTimeout(() => setNote(null), 4_000);
  }

  return (
    <span className="backend-start">
      <button
        type="button"
        className="backend-start-btn backend-start-btn--reload"
        onClick={() => void handleClick()}
        disabled={busy}
        title={BACKEND_RELOAD_BUTTON_TITLE}
        data-testid="backend-reload-btn"
      >
        {busy ? 'Reloading…' : BACKEND_RELOAD_BUTTON_LABEL}
      </button>
      {note && (
        <span className="status-hint" title={note} role="status">
          {note}
        </span>
      )}
      {error && (
        <span className="backend-start-error" title={error} role="status">
          {error.length > 60 ? `${error.slice(0, 60)}…` : error}
        </span>
      )}
    </span>
  );
}
