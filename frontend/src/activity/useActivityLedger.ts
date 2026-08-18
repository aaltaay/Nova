import { useCallback, useEffect, useState } from 'react';
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';
import {
  ACTIVITY_DEFAULT_LIMIT,
  ACTIVITY_DETAIL_PATH,
  ACTIVITY_PATH,
  ACTIVITY_POLL_MS,
} from './constants';
import type { ActivityDetail, ActivityRow } from './types';

interface State {
  rows: ActivityRow[];
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

export function useActivityLedger(): State {
  const [rows, setRows] = useState<ActivityRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);

  const refresh = useCallback(() => setRefreshToken(value => value + 1), []);

  useEffect(() => {
    let active = true;

    async function load() {
      try {
        const res = await novaFetch(
          `${API_BASE_URL}${ACTIVITY_PATH}?limit=${ACTIVITY_DEFAULT_LIMIT}`,
        );
        if (!active) return;
        if (!res.ok) {
          setError(`activity unavailable (HTTP ${res.status})`);
          setLoading(false);
          return;
        }
        setRows((await res.json()) as ActivityRow[]);
        setError(null);
        setLoading(false);
      } catch (err) {
        if (!active) return;
        console.error('[Nova] activity fetch failed', err);
        setError('activity fetch failed -- retrying');
        setLoading(false);
      }
    }

    void load();
    const poll = window.setInterval(load, ACTIVITY_POLL_MS);
    return () => {
      active = false;
      window.clearInterval(poll);
    };
  }, [refreshToken]);

  return { rows, loading, error, refresh };
}

export async function fetchActivityDetail(executionId: string): Promise<ActivityDetail> {
  const res = await novaFetch(`${API_BASE_URL}${ACTIVITY_DETAIL_PATH}/${executionId}`);
  if (!res.ok) {
    throw new Error(`execution detail HTTP ${res.status}`);
  }
  return (await res.json()) as ActivityDetail;
}
