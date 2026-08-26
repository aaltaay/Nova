import { useCallback, useEffect, useState } from 'react';
import { API_BASE_URL } from '../constants';
import { doorTrailLoadError, type DoorTrailEvent } from './formatDoorTrail';

const TRAIL_LIMIT = 80;

export function useGatewayDoorTrail(active = true): {
  rows: DoorTrailEvent[];
  loading: boolean;
  error: string | null;
  refresh: () => void;
} {
  const [rows, setRows] = useState<DoorTrailEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  const refresh = useCallback(() => setTick((n) => n + 1), []);

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch(
          `${API_BASE_URL}/api/ibkr/gateway-trail?limit=${TRAIL_LIMIT}`,
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const body = (await res.json()) as { events?: DoorTrailEvent[] };
        if (!cancelled) {
          setRows(Array.isArray(body.events) ? body.events : []);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(doorTrailLoadError(err));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    const id = window.setInterval(() => void load(), 5_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [active, tick]);

  return { rows, loading, error, refresh };
}
