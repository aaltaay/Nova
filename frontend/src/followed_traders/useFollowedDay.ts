/**
 * The Followed traders page's read: `GET /api/followed-traders/day` every FOLLOWED_REFRESH_MS while the page shows
 * and the window is visible. The backend holds IBKR lines only while it is asked, so a hidden page costs nothing.
 * A failed read keeps the last answer and says so in `error`, and `receivedAt` says when that answer arrived so
 * the page can age it (capture.asOf); a 404 is `off` (no feed configured). The page
 * mounts it under a key per day, so two days' answers are never mixed. `quotes: false` asks the feed only (no IBKR
 * line held: the desk's trade toasts), `everyMs` how often, `enabled: false` asks nothing.
 */
import { useEffect, useState } from 'react';
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';
import { FOLLOWED_DAY_PATH, FOLLOWED_REFRESH_MS, FOLLOWED_SCHEMA_VERSION } from './constants';
import type { FollowedDay } from './types';

export interface FollowedRead {
  data: FollowedDay | null;
  error: string | null;
  /** The backend has no such route: no feed configured. */
  off: boolean;
  /** When `data` arrived (epoch ms, this window's clock); null without one. */
  receivedAt: number | null;
}

/** The wall clock, read again every `everyMs`: a page whose reads have stopped (or hang) still sees time pass. */
export function useNowMs(everyMs: number): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), everyMs);
    return () => window.clearInterval(id);
  }, [everyMs]);
  return now;
}

export function normalizeDay(raw: unknown): FollowedDay | null {
  if (!raw || typeof raw !== 'object') return null;
  const d = raw as Partial<FollowedDay>;
  if (d.schema_version !== FOLLOWED_SCHEMA_VERSION) return null;
  if (!d.feed || typeof d.feed.state !== 'string' || !Array.isArray(d.traders) || !Array.isArray(d.dates)) return null;
  return d as FollowedDay;
}

export function dayUrl(date: string | null, quotes = true): string {
  const q = new URLSearchParams();
  if (date) q.set('date', date);
  if (!quotes) q.set('quotes', '0');
  const query = q.toString();
  return query ? `${FOLLOWED_DAY_PATH}?${query}` : FOLLOWED_DAY_PATH;
}

export interface DayOptions {
  quotes?: boolean;
  everyMs?: number;
  enabled?: boolean;
}

export function useFollowedDay(date: string | null, opts: DayOptions = {}): FollowedRead {
  const { quotes = true, everyMs = FOLLOWED_REFRESH_MS, enabled = true } = opts;
  const [state, setState] = useState<FollowedRead>({ data: null, error: null, off: false, receivedAt: null });

  useEffect(() => {
    if (!enabled) return undefined;
    let cancelled = false;
    let timer: number | undefined;
    const schedule = (ms: number) => {
      if (cancelled) return;
      window.clearTimeout(timer);
      timer = window.setTimeout(() => void read(), ms);
    };

    async function read(): Promise<void> {
      if (cancelled) return;
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') {
        schedule(everyMs);
        return;
      }
      try {
        const res = await novaFetch(`${API_BASE_URL}${dayUrl(date, quotes)}`);
        if (cancelled) return;
        if (res.status === 404) {
          setState({ data: null, error: null, off: true, receivedAt: null });
          return;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const body = normalizeDay(await res.json());
        if (cancelled) return;
        if (!body) throw new Error('the answer is not one this desk can read');
        setState({ data: body, error: null, off: false, receivedAt: Date.now() });
      } catch (e) {
        if (!cancelled) setState((s) => ({ ...s, error: e instanceof Error ? e.message : String(e) }));
      }
      schedule(everyMs);
    }

    const onVisible = () => {
      if (document.visibilityState === 'visible') schedule(0);
    };
    document.addEventListener('visibilitychange', onVisible);
    void read();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [date, quotes, everyMs, enabled]);

  return state;
}
