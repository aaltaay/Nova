import { useCallback, useEffect, useState } from 'react';
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';
import {
  ACTIVITY_DEFAULT_LIMIT,
  ACTIVITY_POLL_MS,
  ACTIVITY_TRAIL_PATH,
} from './constants';
import type { TrailItem, TrailPayload } from './types';

interface State {
  items: TrailItem[];
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

export function useActivityTrail(): State {
  const [items, setItems] = useState<TrailItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);

  const refresh = useCallback(() => setRefreshToken(value => value + 1), []);

  useEffect(() => {
    let active = true;

    async function load() {
      try {
        const res = await novaFetch(
          `${API_BASE_URL}${ACTIVITY_TRAIL_PATH}?limit=${ACTIVITY_DEFAULT_LIMIT}`,
        );
        if (!active) return;
        if (!res.ok) {
          setError(`trail unavailable (HTTP ${res.status})`);
          setLoading(false);
          return;
        }
        const body = (await res.json()) as TrailPayload;
        setItems(Array.isArray(body.items) ? body.items : []);
        setError(null);
        setLoading(false);
      } catch (err) {
        if (!active) return;
        console.error('[Nova] activity trail fetch failed', err);
        setError('trail fetch failed -- retrying');
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

  return { items, loading, error, refresh };
}