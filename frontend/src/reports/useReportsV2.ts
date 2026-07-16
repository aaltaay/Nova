/** Fetches Reports v2 analytics (tags, R-multiples, drawdown). */
import { useEffect, useRef, useState } from 'react';
import { API_BASE_URL, JOURNAL_POLL_INTERVAL_MS } from '../constants';
import type { DrawdownResponse, RMultiplesResponse, TagsResponse } from './types';

const JOURNAL_API = `${API_BASE_URL}/api/journal`;

export interface UseReportsV2Return {
  tags: TagsResponse | null;
  rMultiples: RMultiplesResponse | null;
  drawdown: DrawdownResponse | null;
  loading: boolean;
  error: string | null;
}

export function useReportsV2(enabled: boolean, includeMock: boolean): UseReportsV2Return {
  const [tags, setTags] = useState<TagsResponse | null>(null);
  const [rMultiples, setRMultiples] = useState<RMultiplesResponse | null>(null);
  const [drawdown, setDrawdown] = useState<DrawdownResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;

    async function poll() {
      if (inFlight.current) return;
      inFlight.current = true;
      try {
        const mockQ = includeMock ? '?include_mock=true' : '';
        const [tagsRes, rRes, ddRes] = await Promise.all([
          fetch(`${JOURNAL_API}/tags${mockQ}`),
          fetch(`${JOURNAL_API}/r-multiples${mockQ}`),
          fetch(`${JOURNAL_API}/drawdown${mockQ}`),
        ]);
        if (!tagsRes.ok || !rRes.ok || !ddRes.ok) {
          throw new Error('Failed to load reports analytics');
        }
        const [tagsJson, rJson, ddJson] = await Promise.all([
          tagsRes.json() as Promise<TagsResponse>,
          rRes.json() as Promise<RMultiplesResponse>,
          ddRes.json() as Promise<DrawdownResponse>,
        ]);
        if (!cancelled) {
          setTags(tagsJson);
          setRMultiples(rJson);
          setDrawdown(ddJson);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load reports analytics');
        }
      } finally {
        inFlight.current = false;
        if (!cancelled) setLoading(false);
      }
    }

    setLoading(true);
    poll();
    const interval = setInterval(poll, JOURNAL_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [enabled, includeMock]);

  return { tags, rMultiples, drawdown, loading, error };
}
