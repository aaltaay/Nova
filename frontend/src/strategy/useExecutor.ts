/** Polls executor status and exposes mode / staged / emergency actions (Nova OS P4). */
import { useCallback, useEffect, useRef, useState } from 'react';
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL, EXECUTOR_POLL_INTERVAL_MS, NOVA_OS_FLATTEN_CONFIRM_TOKEN } from '../constants';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import type { ExecutorStatus } from './types';

const EXECUTOR_API = `${API_BASE_URL}/api/strategy/executor`;

export interface UseExecutorReturn {
  status: ExecutorStatus | null;
  loading: boolean;
  error: string | null;
  actionError: string | null;
  arm: () => Promise<void>;
  disarm: () => Promise<void>;
  setMode: (mode: string) => Promise<void>;
  killSwitch: () => Promise<void>;
  resetKillSwitch: () => Promise<void>;
  approveStaged: (id: string) => Promise<void>;
  rejectStaged: (id: string, reason?: string) => Promise<void>;
  cancelWorkingEntry: (symbol: string) => Promise<void>;
  flatten: () => Promise<void>;
}

const SAMPLE_NOOP = async () => {};

export function useExecutor(enabled: boolean): UseExecutorReturn {
  const sample = useSampleDataOptional();
  const [status, setStatus] = useState<ExecutorStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const inFlight = useRef(false);

  const refresh = useCallback(async () => {
    if (sample || inFlight.current) return;
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
  }, [sample]);

  const postJson = useCallback(async (path: string, body?: object) => {
    if (sample) return;
    try {
      const res = await novaFetch(`${EXECUTOR_API}/${path}`, {
        method: 'POST',
        headers: body ? { 'Content-Type': 'application/json' } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const detail = typeof data.detail === 'string' ? data.detail : `HTTP ${res.status}`;
        throw new Error(detail);
      }
      setStatus(data);
      setActionError(null);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : `Failed to ${path}`);
    }
  }, [sample]);

  useEffect(() => {
    if (sample || !enabled) return;
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
  }, [sample, enabled, refresh]);

  if (sample) {
    return {
      status: {
        disclosure: 'Sample data — automation fixtures only; nothing places.',
        armed: false,
        control_mode: 'signal',
        effective_mode: 'signal',
        kill_switch_tripped: false,
        ibkr_connected: true,
        ibkr_mode: 'paper',
        staged: [],
        open_positions: [],
      },
      loading: false,
      error: null,
      actionError: null,
      arm: SAMPLE_NOOP,
      disarm: SAMPLE_NOOP,
      setMode: async (_mode: string) => {},
      killSwitch: SAMPLE_NOOP,
      resetKillSwitch: SAMPLE_NOOP,
      approveStaged: SAMPLE_NOOP,
      rejectStaged: SAMPLE_NOOP,
      cancelWorkingEntry: SAMPLE_NOOP,
      flatten: SAMPLE_NOOP,
    };
  }

  return {
    status,
    loading,
    error,
    actionError,
    arm: () => postJson('arm'),
    disarm: () => postJson('disarm'),
    setMode: (mode: string) => postJson('mode', { mode }),
    killSwitch: () => postJson('kill-switch'),
    resetKillSwitch: () => postJson('reset-kill-switch'),
    approveStaged: (id: string) => postJson(`staged/${encodeURIComponent(id)}/approve`),
    rejectStaged: (id: string, reason = 'rejected') =>
      postJson(`staged/${encodeURIComponent(id)}/reject`, { reason }),
    cancelWorkingEntry: (symbol: string) => postJson('cancel-working-entry', { symbol }),
    flatten: () => postJson('flatten', { confirm_token: NOVA_OS_FLATTEN_CONFIRM_TOKEN }),
  };
}
