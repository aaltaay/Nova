import { useCallback, useEffect, useState } from 'react';
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';
import {
  EXECUTION_LATENCY_PATH,
  LATENCY_METRICS_POLL_MS,
  OPERATION_METRICS_PATH,
} from './constants';
import { parseLatencyDashboard } from './model';
import type { LatencyDashboardSnapshot } from './types';

interface LatencyMetricsState {
  snapshot: LatencyDashboardSnapshot | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

async function readJson(path: string): Promise<unknown> {
  const response = await novaFetch(`${API_BASE_URL}${path}`);
  if (!response.ok) {
    throw new Error(`${path} returned HTTP ${response.status}`);
  }
  return response.json();
}

export function useLatencyMetrics(): LatencyMetricsState {
  const [snapshot, setSnapshot] = useState<LatencyDashboardSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);

  const refresh = useCallback(() => setRefreshToken(value => value + 1), []);

  useEffect(() => {
    let active = true;

    async function load() {
      const [operations, execution] = await Promise.allSettled([
        readJson(OPERATION_METRICS_PATH),
        readJson(EXECUTION_LATENCY_PATH),
      ]);
      if (!active) return;

      const operationsValue = operations.status === 'fulfilled'
        ? operations.value
        : {};
      const executionValue = execution.status === 'fulfilled'
        ? execution.value
        : {};
      const messages = [operations, execution]
        .filter((item): item is PromiseRejectedResult => item.status === 'rejected')
        .map(item => item.reason instanceof Error ? item.reason.message : String(item.reason));

      if (
        operations.status === 'rejected'
        && execution.status === 'rejected'
      ) {
        setError(messages.join(' · '));
      } else {
        setSnapshot(parseLatencyDashboard(
          operationsValue,
          executionValue,
          Date.now(),
        ));
        setError(messages.length > 0 ? `Partial data: ${messages.join(' · ')}` : null);
      }
      setLoading(false);
    }

    void load();
    const poll = window.setInterval(load, LATENCY_METRICS_POLL_MS);
    return () => {
      active = false;
      window.clearInterval(poll);
    };
  }, [refreshToken]);

  return { snapshot, loading, error, refresh };
}
