/**
 * App-level host so a market-wide circuit breaker is visible on Scanner and
 * Trader. Display only -- does not block Place.
 */
import { useEffect, useState } from 'react';
import { API_BASE_URL } from '../constants';
import { HALT_DESK_POLL_MS } from '../constantGroups/halt_eta';
import { MwcbBanner } from './MwcbBanner';
import type { MwcbDesk } from './mwcbBanner';

function readMwcb(body: unknown): MwcbDesk {
  if (!body || typeof body !== 'object') return null;
  const raw = (body as { mwcb?: unknown }).mwcb;
  if (!raw || typeof raw !== 'object') return null;
  const row = raw as { level?: unknown; reason_code?: unknown; stale?: unknown; source?: unknown };
  const level = Number(row.level);
  if (level !== 1 && level !== 2 && level !== 3) return null;
  if (typeof row.reason_code !== 'string' || !row.reason_code) return null;
  return {
    level,
    reason_code: row.reason_code,
    stale: Boolean(row.stale),
    source: typeof row.source === 'string' ? row.source : undefined,
  };
}

export function MwcbBannerHost({
  pollMs = HALT_DESK_POLL_MS,
  fetchImpl = fetch,
}: {
  pollMs?: number;
  fetchImpl?: typeof fetch;
} = {}) {
  const [mwcb, setMwcb] = useState<MwcbDesk>(null);

  useEffect(() => {
    let cancelled = false;
    const pull = async () => {
      try {
        const res = await fetchImpl(`${API_BASE_URL}/api/halts/desk`);
        if (!res.ok) return;
        const body = await res.json();
        if (!cancelled) setMwcb(readMwcb(body));
      } catch {
        /* keep last-known MWCB; RSS down is marked stale by the API */
      }
    };
    void pull();
    const id = window.setInterval(() => { void pull(); }, pollMs);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [fetchImpl, pollMs]);

  return <MwcbBanner mwcb={mwcb} />;
}
