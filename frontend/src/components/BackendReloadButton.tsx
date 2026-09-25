/**
 * Restart the local Nova API while the dashboard is connected — dev / desktop only.
 * Uses the same kill+restart path as BackendStartButton (Start-NovaApi.ps1 / Electron sidecar).
 */
import { useState } from 'react';
import { backendRemedy } from '../../electron/appTitle.mjs';
import {
  BACKEND_RELOAD_BUTTON_LABEL,
  BACKEND_RELOAD_BUTTON_TITLE,
  BACKEND_RELOAD_CONFIRM_MESSAGE,
  BACKEND_RELOAD_CONFIRM_TITLE,
  BACKEND_RELOAD_STILL_OLDER_NOTE_MS,
  BACKEND_RELOAD_WHY_BUSY,
  backendReloadSameCodeWarning,
  backendReloadStillOlderNote,
} from '../constants';
import { confirmApp } from '../ux';
import {
  currentBackendCheckoutTag,
  currentBackendReleaseTag,
  refreshBackendReleaseTag,
} from '../utils/backendReleaseTag';
import { novaRendererReleaseTag } from '../utils/novaReleaseTag';
import { startLocalApi } from '../utils/startLocalApi';

interface Props {
  /** Called after a successful restart so scanner/health can refresh. */
  onReloaded?: () => void;
}

/**
 * The backend, its checkout and this desk when a restart cannot reach the desk's revision --
 * the checkout holds nothing newer than what runs (operator report 2026-09-25) -- else null.
 */
function restartLoadsNothingNewer(): { running: string; checkout: string; desk: string } | null {
  const running = currentBackendReleaseTag();
  const checkout = currentBackendCheckoutTag();
  const desk = novaRendererReleaseTag();
  if (!running || !checkout || backendRemedy(running, desk, checkout) !== 'pull') return null;
  return { running, checkout, desk };
}

export function BackendReloadButton({ onReloaded }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  async function handleClick() {
    if (busy) return;
    // What would a restart load? Ask now, not a minute ago.
    await refreshBackendReleaseTag();
    const before = restartLoadsNothingNewer();
    const ok = await confirmApp({
      title: BACKEND_RELOAD_CONFIRM_TITLE,
      message: before
        ? `${BACKEND_RELOAD_CONFIRM_MESSAGE}\n\n${backendReloadSameCodeWarning(before.running, before.checkout, before.desk)}`
        : BACKEND_RELOAD_CONFIRM_MESSAGE,
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
    // Name the revision now answering (the window title shows it too), and say when the
    // restart could not reach this desk's.
    await refreshBackendReleaseTag();
    const now = currentBackendReleaseTag();
    const after = restartLoadsNothingNewer();
    if (after) {
      setNote(backendReloadStillOlderNote(after.running, after.checkout));
    } else {
      setNote(now ? `Backend reloaded · now ${now}` : 'Backend reloaded');
    }
    onReloaded?.();
    window.setTimeout(() => setNote(null), after ? BACKEND_RELOAD_STILL_OLDER_NOTE_MS : 4_000);
  }

  return (
    <span className="backend-start">
      <button
        type="button"
        className="backend-start-btn backend-start-btn--reload"
        onClick={() => void handleClick()}
        disabled={busy}
        data-why={busy ? BACKEND_RELOAD_WHY_BUSY : undefined}
        title={busy ? undefined : BACKEND_RELOAD_BUTTON_TITLE}
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
