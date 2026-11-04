/** Fetches Reports v2 analytics (tags, R-multiples, drawdown) for the venue and view in `viewQuery` (ADR 069). */
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

export function useReportsV2(
  enabled: boolean,
  includeMock: boolean,
  refreshToken = 0,
  viewQuery = '',
): UseReportsV2Return {
  const [tags, setTags] = useState<TagsResponse | null>(null);
  const [rMultiples, setRMultiples] = useState<RMultiplesResponse | null>(null);
  const [drawdown, setDrawdown] = useState<DrawdownResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const shownQuery = useRef(viewQuery);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    if (shownQuery.current !== viewQuery) {    // a new pick: never the old pick's figures under it
      shownQuery.current = viewQuery;
      setTags(null);
      setRMultiples(null);
      setDrawdown(null);
    }
    // Per effect run (QA V42): see useCalendar -- a shared flag made the first
    // poll wait out a whole interval after any re-run.
    const inFlight = { current: false };

    async function poll() {
      if (inFlight.current) return;
      inFlight.current = true;
      try {
        const query = [includeMock ? 'include_mock=true' : '', viewQuery].filter(Boolean).join('&');
        const mockQ = query ? `?${query}` : '';
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
  }, [enabled, includeMock, refreshToken, viewQuery]);

  return { tags, rMultiples, drawdown, loading, error };
}
