/**
 * Shown next to "Backend unreachable" — one click restarts the local API
 * (Electron sidecar or Vite-dev Start-NovaApi.ps1).
 */
import { useState } from 'react';
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

  async function handleClick() {
    if (busy) return;
    setBusy(true);
    setError(null);
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
    'Restart the local Nova API on port 8000',
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
      {error && (
        <span className="backend-start-error" title={error} role="status">
          {error.length > 60 ? `${error.slice(0, 60)}…` : error}
        </span>
      )}
    </span>
  );
}
