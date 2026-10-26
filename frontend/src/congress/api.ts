/**
 * The Congress page's reads (ADR 066). The board is polled while the page shows and the window is visible (faster
 * while the reader is busy or the agreement is pending); the other views ask once per open. A failed read keeps the
 * last good answer and says so. The sample desk reads nothing live. The one price -- a stock's move over the period
 * -- is IBKR's daily bars through the desk's own `/api/ticker/{symbol}/bars`.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';
import { useSampleRoute } from '../sample_data/useSampleRoute';
import {
  CONGRESS_BARS_PATH, CONGRESS_BOARD_PATH, CONGRESS_BUSY_POLL_MS, CONGRESS_CONSENT_PATH, CONGRESS_MEMBER_PATH,
  CONGRESS_FILLING_RETRY_MS, CONGRESS_MEMBERS_PATH, CONGRESS_MOVES_REFRESH_MS, CONGRESS_POLL_MS, CONGRESS_SCHEMA_VERSION, CONGRESS_TRADES_PATH,
} from './constants';
import {
  sampleCongressBoard, sampleCongressMember, sampleCongressMembers, sampleCongressTicker,
} from './sampleCongress';
import type { Board, Consent, Filter, MemberAnswer, MembersAnswer, TickerAnswer } from './types';

export interface Read<T> {
  data: T | null;
  error: string | null;
  /** The backend has no such route (an API from before ADR 066), or no such member. */
  missing: boolean;
  reload: () => void;
}

function current<T extends { schema_version?: number }>(raw: unknown): T | null {
  return raw && typeof raw === 'object' && (raw as T).schema_version === CONGRESS_SCHEMA_VERSION ? (raw as T) : null;
}

export function boardUrl(filter: Filter, members: readonly string[] | null): string {
  const q = new URLSearchParams({ filter });
  if (members) q.set('members', members.join(','));
  return `${CONGRESS_BOARD_PATH}?${q.toString()}`;
}

const keptBoards = new Map<string, Board>();

export function resetKeptCongressForTests(): void {
  keptBoards.clear();
}

function busy(b: Board | null): boolean {
  return !b || b.consent.state !== 'given' || b.sources.some((s) => s.state === 'reading' || s.state === 'waiting');
}

/** The overview for a filter (and, on Following, its members), polled while shown. */
export function useCongressBoard(filter: Filter, members: readonly string[] | null): Read<Board> {
  const sample = useSampleRoute();
  const url = sample ? null : boardUrl(filter, members);
  const [state, setState] = useState<Omit<Read<Board>, 'reload'>>(() => ({
    data: url ? keptBoards.get(url) ?? null : null, error: null, missing: false,
  }));
  const [tick, setTick] = useState(0);
  const lastRef = useRef<Board | null>(state.data);

  useEffect(() => {
    if (!url) return undefined;
    let cancelled = false;
    let timer: number | undefined;
    const kept = keptBoards.get(url);
    if (kept && kept !== lastRef.current) {
      lastRef.current = kept;
      setState((s) => ({ ...s, data: kept }));
    }
    const schedule = (ms: number) => {
      if (!cancelled) timer = window.setTimeout(() => void read(), ms);
    };
    async function read(): Promise<void> {
      if (cancelled) return;
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') {
        schedule(CONGRESS_POLL_MS);
        return;
      }
      try {
        const res = await novaFetch(`${API_BASE_URL}${url}`);
        if (cancelled) return;
        if (res.status === 404) {
          setState((s) => ({ ...s, missing: true }));
          return;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const body = current<Board>(await res.json());
        if (cancelled) return;
        if (!body) throw new Error('the answer is not one this desk can read');
        lastRef.current = body;
        keptBoards.set(url as string, body);
        setState({ data: body, error: null, missing: false });
      } catch (e) {
        if (!cancelled) setState((s) => ({ ...s, error: `The Congress page did not load: ${e instanceof Error ? e.message : String(e)}` }));
      }
      schedule(busy(lastRef.current) ? CONGRESS_BUSY_POLL_MS : CONGRESS_POLL_MS);
    }
    const onVisible = () => {
      if (document.visibilityState === 'visible') {
        window.clearTimeout(timer);
        schedule(0);
      }
    };
    document.addEventListener('visibilitychange', onVisible);
    void read();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [url, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  const sampleRead = useMemo(() => ({ data: sample ? sampleCongressBoard() : null, error: null, missing: false }), [sample]);
  return { ...(sample ? sampleRead : state), reload };
}

interface Asked<T> {
  path: string | null;
  data: T | null;
  error: string | null;
  missing: boolean;
}

/** One read of a path when it changes (members, a member, a stock); the sample desk answers from its own data. An
 *  answer belongs to the path it was asked for: a new path shows nothing until its own answer, never the last one's. */
function useOnce<T extends { schema_version?: number }>(path: string | null, sampled: () => T | null): Read<T> {
  const sample = useSampleRoute();
  const [state, setState] = useState<Asked<T>>({ path: null, data: null, error: null, missing: false });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (sample || !path) return undefined;
    let cancelled = false;
    setState((s) => (s.path === path ? { ...s, error: null } : { path, data: null, error: null, missing: false }));
    novaFetch(`${API_BASE_URL}${path}`)
      .then(async (res) => {
        if (cancelled) return;
        if (res.status === 404) {
          setState({ path, data: null, error: null, missing: true });
          return;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const body = current<T>(await res.json());
        if (!body) throw new Error('the answer is not one this desk can read');
        if (!cancelled) setState({ path, data: body, error: null, missing: false });
      })
      .catch((e) => {
        if (!cancelled) {
          setState((s) => (s.path === path ? { ...s, error: `Did not load: ${e instanceof Error ? e.message : String(e)}` } : s));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [sample, path, tick]);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  const sampleData = useMemo(() => (sample ? sampled() : null), [sample, sampled]);
  if (sample) return { data: sampleData, error: null, missing: sampleData == null, reload };
  const mine = state.path === path;
  return { data: mine ? state.data : null, error: mine ? state.error : null, missing: mine && state.missing, reload };
}

export function useCongressMembers(): Read<MembersAnswer> {
  return useOnce<MembersAnswer>(CONGRESS_MEMBERS_PATH, sampleCongressMembers);
}

export function useCongressMember(bioguide: string): Read<MemberAnswer> {
  const sampled = useCallback(() => sampleCongressMember(bioguide), [bioguide]);
  return useOnce<MemberAnswer>(`${CONGRESS_MEMBER_PATH}/${encodeURIComponent(bioguide)}`, sampled);
}

export function useCongressTicker(ticker: string): Read<TickerAnswer> {
  const sampled = useCallback(() => sampleCongressTicker(ticker), [ticker]);
  return useOnce<TickerAnswer>(`${CONGRESS_TRADES_PATH}?${new URLSearchParams({ ticker }).toString()}`, sampled);
}

export async function postConsent(accept: boolean): Promise<Consent> {
  const res = await novaFetch(`${API_BASE_URL}${CONGRESS_CONSENT_PATH}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ accept }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const body = (await res.json()) as { consent: Consent };
  return body.consent;
}

export interface Move {
  state: 'reading' | 'ok' | 'none';
  pct: number | null;
}

interface Bar {
  t: string;
  c: number;
}

/** A stock's move from the last close before `from` to the latest close, from IBKR's daily bars (pure). */
export function moveFrom(bars: readonly Bar[], from: string): number | null {
  const before = bars.filter((b) => b.t.slice(0, 10) < from);
  const base = before.length ? before[before.length - 1].c : null;
  const last = bars.length ? bars[bars.length - 1].c : null;
  return base && last ? (100 * (last - base)) / base : null;
}

const SAMPLE_MOVES: Record<string, number> = { AAPL: 27, MSFT: 10, NVDA: 17, AMZN: 8, META: 11, HD: -14, PG: 9, ACN: -21 };
const keptBars = new Map<string, { at: number; bars: Bar[] | null; filling: boolean }>();

/** Each ticker's move since `from` (IBKR's daily bars, read once per ticker per few minutes). */
export function usePeriodMoves(tickers: readonly string[], from: string): Record<string, Move> {
  const sample = useSampleRoute();
  const key = tickers.join(',');
  const [moves, setMoves] = useState<Record<string, Move>>({});
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (sample || !tickers.length) return undefined;
    let cancelled = false;
    let again: number | undefined;
    const now = Date.now();
    const next: Record<string, Move> = {};
    const answer = (t: string) => {
      const k = keptBars.get(t);
      if (!k) return { state: 'reading', pct: null } as Move;
      if (!k.bars || !k.bars.length) return { state: k.filling ? 'reading' : 'none', pct: null } as Move;
      const pct = moveFrom(k.bars, from);
      return { state: pct == null ? 'none' : 'ok', pct } as Move;
    };
    tickers.forEach((t) => {
      next[t] = answer(t);
    });
    setMoves(next);
    tickers
      .filter((t) => {
        const k = keptBars.get(t);
        return !k || k.filling || now - k.at > CONGRESS_MOVES_REFRESH_MS;
      })
      .forEach((t) => {
        novaFetch(`${API_BASE_URL}${CONGRESS_BARS_PATH(t)}`)
          .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
          .then((body: { bars?: Bar[]; coverage?: { filling?: boolean } }) => {
            keptBars.set(t, { at: Date.now(), bars: Array.isArray(body.bars) ? body.bars : null,
              filling: Boolean(body.coverage?.filling) });
          })
          .catch(() => keptBars.set(t, { at: Date.now(), bars: null, filling: false }))
          .finally(() => {
            if (cancelled) return;
            setMoves((m) => ({ ...m, [t]: answer(t) }));
            // IBKR's history is still filling this one: ask again shortly
            if (keptBars.get(t)?.filling && again === undefined) {
              again = window.setTimeout(() => setTick((n) => n + 1), CONGRESS_FILLING_RETRY_MS);
            }
          });
      });
    return () => {
      cancelled = true;
      window.clearTimeout(again);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `key` stands for the tickers' contents
  }, [sample, key, from, tick]);
  return useMemo(() => {
    if (!sample) return moves;
    return Object.fromEntries(tickers.map((t) => [t, { state: 'ok', pct: SAMPLE_MOVES[t] ?? null } as Move]));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `key` stands for the tickers' contents
  }, [sample, moves, key]);
}
