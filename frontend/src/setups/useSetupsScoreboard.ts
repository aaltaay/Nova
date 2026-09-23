/** Polls `/api/setups/scoreboard` while the Setups scoreboard is on screen. The
 * sample desk reads the Nova Marketing Sample Data scoreboard instead. */
import { useEffect, useRef, useState } from 'react';
import { API_BASE_URL, SETUPS_SCOREBOARD_PATH, SETUPS_SCOREBOARD_POLL_MS } from '../constants';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import { SAMPLE_SETUPS_SCOREBOARD } from '../sample_data/sampleSetups';
import type { Scoreboard } from './types';

export interface SetupsScoreboardState {
  data: Scoreboard | null;
  error: string | null;
  loading: boolean;
}

export function useSetupsScoreboard(enabled: boolean, days: number): SetupsScoreboardState {
  const sample = useSampleDataOptional();
  const [data, setData] = useState<Scoreboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const inFlight = useRef(false);

  useEffect(() => {
    if (sample || !enabled) return;
    let cancelled = false;
    setLoading(true);

    async function poll() {
      if (inFlight.current) return;
      inFlight.current = true;
      try {
        const res = await fetch(`${API_BASE_URL}${SETUPS_SCOREBOARD_PATH}?days=${days}`);
        if (!res.ok) {
          let detail = `HTTP ${res.status}`;
          try {
            const body = await res.json();
            if (typeof body?.detail === 'string') detail = body.detail;
          } catch {
            // no JSON body: keep the status line
          }
          throw new Error(detail);
        }
        const body = (await res.json()) as Scoreboard;
        if (!cancelled) {
          setData(body);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError(`Scoreboard unavailable: ${e instanceof Error ? e.message : String(e)}`);
      } finally {
        inFlight.current = false;
        if (!cancelled) setLoading(false);
      }
    }

    void poll();
    const id = window.setInterval(() => void poll(), SETUPS_SCOREBOARD_POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [sample, enabled, days]);

  if (sample) return { data: SAMPLE_SETUPS_SCOREBOARD, error: null, loading: false };
  return { data, error, loading };
}
