/** Polls the paper-execution engine's status and exposes the arm/disarm/kill-switch
 * actions. Every action call re-fetches status immediately so the UI never shows a
 * stale armed/disarmed state after a click. See backend/routes/executor.py. */
import { useCallback, useEffect, useRef, useState } from 'react';
import { API_BASE_URL, EXECUTOR_POLL_INTERVAL_MS } from '../constants';
import type { ExecutorStatus } from './types';

const EXECUTOR_API = `${API_BASE_URL}/api/strategy/executor`;

export interface UseExecutorReturn {
  status: ExecutorStatus | null;
  loading: boolean;
  error: string | null;
  actionError: string | null;
  arm: () => Promise<void>;
  disarm: () => Promise<void>;
  killSwitch: () => Promise<void>;
  resetKillSwitch: () => Promise<void>;
}

export function useExecutor(enabled: boolean): UseExecutorReturn {
  const [status, setStatus] = useState<ExecutorStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const inFlight = useRef(false);

  const refresh = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      const res = await fetch(`${EXECUTOR_API}/status`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setStatus(await res.json());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load executor status');
    } finally {
      inFlight.current = false;
      setLoading(false);
    }
  }, []);

  const postAction = useCallback(async (path: string) => {
    try {
      const res = await fetch(`${EXECUTOR_API}/${path}`, { method: 'POST' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setStatus(await res.json());
      setActionError(null);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : `Failed to ${path}`);
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    const tick = () => {
      if (!cancelled) refresh();
    };
    tick();
    const interval = setInterval(tick, EXECUTOR_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [enabled, refresh]);

  return {
    status,
    loading,
    error,
    actionError,
    arm: () => postAction('arm'),
    disarm: () => postAction('disarm'),
    killSwitch: () => postAction('kill-switch'),
    resetKillSwitch: () => postAction('reset-kill-switch'),
  };
}
