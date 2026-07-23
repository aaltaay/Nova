/**
 * Shown next to Backend unreachable — one click restarts the local API
 * (Electron sidecar or Vite-dev Start-NovaApi.ps1).
 * Also auto-heals once per session on API_WEDGED / API_DOWN.
 */
import { useEffect, useRef, useState } from 'react';
import {
  BACKEND_DIAG_FLAG_DOWN,
  BACKEND_DIAG_FLAG_WEDGED,
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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [autoNote, setAutoNote] = useState<string | null>(null);
  const autoTriedRef = useRef(false);
  const onStartedRef = useRef(onStarted);
  onStartedRef.current = onStarted;

  useEffect(() => {
    if (autoTriedRef.current) return;
    if (flag !== BACKEND_DIAG_FLAG_WEDGED && flag !== BACKEND_DIAG_FLAG_DOWN) {
      return;
    }
    autoTriedRef.current = true;
    let cancelled = false;
    setBusy(true);
    setAutoNote('Auto-restarting API…');
    setError(null);
    void maybeAutoHealBackend(flag).then((result) => {
      if (cancelled) return;
      setBusy(false);
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
    setBusy(true);
    setError(null);
    setAutoNote(null);
    const result = await startLocalApi();
    setBusy(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    onStarted?.();
  }

  const title = [
    flag ? `Flag ${flag}` : null,
    flagHint,
    'Restart the local Nova API on port 8000 (auto once on WEDGED/DOWN)',
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
        title={title}
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
