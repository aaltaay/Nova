import { useEffect, useState } from 'react';
import { API_BASE_URL } from '../constants';
import type { NewsImpactVerdict } from '../types/newsImpact';

const API = `${API_BASE_URL}/api`;

/**
 * Fetch the explicit news-impact verdict for a symbol.
 * Prefer the `news_impact` field on ticker detail when present; this hook is
 * the fallback / Catalysts-path entry point (GET /api/news/impact/{symbol}).
 */
export function useNewsImpact(symbol: string | null): {
  verdict: NewsImpactVerdict | null;
  loading: boolean;
  error: string | null;
} {
  const [verdict, setVerdict] = useState<NewsImpactVerdict | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!symbol) {
      setVerdict(null);
      setLoading(false);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetch(`${API}/news/impact/${encodeURIComponent(symbol)}`)
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json() as Promise<NewsImpactVerdict>;
      })
      .then((data) => {
        if (!cancelled) {
          setVerdict(data);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setVerdict(null);
          setLoading(false);
          setError(err instanceof Error ? err.message : 'Failed to load news impact');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  return { verdict, loading, error };
}
