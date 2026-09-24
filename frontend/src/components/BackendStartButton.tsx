/**
 * Shown next to Backend unreachable — one click restarts the local API
 * (Electron sidecar or Vite-dev Start-NovaApi.ps1).
 * Also auto-heals once per session on API_DOWN only (never WEDGED -- ADR 010).
 */
import { useEffect, useRef, useState } from 'react';
import {
  BACKEND_DIAG_FLAG_DOWN,
  BACKEND_START_WHY_AUTO,
  BACKEND_START_WHY_BUSY,
} from '../constants';
import { maybeAutoHealBackend } from '../utils/backendAutoHeal';
import { startLocalApi } from '../utils/startLocalApi';

interface Props {
  /** Called after a successful start so scanner/health can refresh immediately. */
  onStarted?: () => void;
  /** Active outage flag (API_WEDGED / API_DOWN / …). */
  flag?: string;
  flagHint?: string;
}

export function BackendStartButton({ onStarted, flag, flagHint }: Props) {
  // Why the button is locked while a start runs (ux/whyTip.ts): the auto-heal or the operator's own click.
  const [busyWhy, setBusyWhy] = useState<string | null>(null);
  const busy = busyWhy !== null;
  const [error, setError] = useState<string | null>(null);
  const [autoNote, setAutoNote] = useState<string | null>(null);
  const autoTriedRef = useRef(false);
  const onStartedRef = useRef(onStarted);
  onStartedRef.current = onStarted;

  useEffect(() => {
    if (autoTriedRef.current) return;
    if (flag !== BACKEND_DIAG_FLAG_DOWN) {
      return;
    }
    autoTriedRef.current = true;
    let cancelled = false;
    setBusyWhy(BACKEND_START_WHY_AUTO);
    setAutoNote('Auto-restarting API…');
    setError(null);
    void maybeAutoHealBackend(flag).then((result) => {
      if (cancelled) return;
      setBusyWhy(null);
      if (!result) {
        setAutoNote(null);
        return;
      }
      if (!result.ok) {
        setAutoNote(null);
        setError(result.error);
        return;
      }
      setAutoNote('API restarted');
      onStartedRef.current?.();
      window.setTimeout(() => {
        if (!cancelled) setAutoNote(null);
      }, 4_000);
    });
    return () => {
      cancelled = true;
    };
  }, [flag]);

  async function handleClick() {
    if (busy) return;
    setBusyWhy(BACKEND_START_WHY_BUSY);
    setError(null);
    setAutoNote(null);
    const result = await startLocalApi();
    setBusyWhy(null);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    onStarted?.();
  }

  const title = [
    flag ? `Flag ${flag}` : null,
    flagHint,
    'Restart the local Nova API on port 8000 (auto once on API_DOWN only)',
  ]
    .filter(Boolean)
    .join(' — ');

  return (
    <span className="backend-start">
      <button
        type="button"
        className="backend-start-btn"
        onClick={() => void handleClick()}
        disabled={busy}
        data-why={busyWhy ?? undefined}
        title={busy ? undefined : title}
      >
        {busy ? 'Starting…' : 'Start API'}
      </button>
      {autoNote && (
        <span className="status-hint" title={autoNote} role="status">
          {autoNote}
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
