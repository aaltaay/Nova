/** Polls GET /api/strategy/watchlist on an interval — same REST-poll pattern as scanner tabs. */
import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { API_BASE_URL, WATCHLIST_POLL_INTERVAL_MS } from '../constants';
import { simClockResource, useSimReplayDesk, useSimReplayPlayhead } from '../sim';
import type { WatchlistEntry, WatchlistReplay } from './types';

const API = `${API_BASE_URL}/api/strategy`;
const WATCHLIST_UNREADABLE = 'Watchlist reply was not readable';

export interface UseWatchlistReturn {
  entries: WatchlistEntry[];
  loading: boolean;
  error: string | null;
  source: 'live' | 'replay' | null;
  replay: WatchlistReplay | null;
}

export interface ParsedWatchlistResponse {
  entries: WatchlistEntry[];
  source: 'live' | 'replay';
  replay: WatchlistReplay | null;
}

let currentReplay: WatchlistReplay | null = null;
const replayListeners = new Set<() => void>();

function publishWatchlistReplay(next: WatchlistReplay | null): void {
  if (currentReplay === next) return;
  currentReplay = next;
  for (const fn of [...replayListeners]) fn();
}

function subscribeWatchlistReplay(fn: () => void): () => void {
  replayListeners.add(fn);
  return () => {
    replayListeners.delete(fn);
  };
}

function getWatchlistReplaySnapshot(): WatchlistReplay | null {
  return currentReplay;
}

/** Current replay provenance from the active `useWatchlist` poll, or `override` when supplied. */
export function useWatchlistReplay(override?: WatchlistReplay | null): WatchlistReplay | null {
  const shared = useSyncExternalStore(subscribeWatchlistReplay, getWatchlistReplaySnapshot);
  return override !== undefined ? override : shared;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value != null && typeof value === 'object' && !Array.isArray(value);
}

const finiteNum = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const nonEmptyStr = (v: unknown): string | null => (typeof v === 'string' && v.trim() ? v : null);

export function readWatchlistReplay(raw: unknown): WatchlistReplay | null {
  if (!isRecord(raw)) return null;
  const sessionDate = nonEmptyStr(raw.session_date);
  const at = finiteNum(raw.at);
  if (!sessionDate || at == null) return null;
  const absent = nonEmptyStr(raw.absent);
  const covered = typeof raw.covered === 'boolean' ? raw.covered : absent == null;
  return {
    session_date: sessionDate,
    at,
    minute_ts: finiteNum(raw.minute_ts),
    board_source: nonEmptyStr(raw.board_source),
    covered,
    absent,
  };
}

/**
 * The entries of a /api/strategy/watchlist reply, each one shaped enough to
 * render (WatchCell reads five_pillars.pillars and composite_score).
 *
 * QA C15: a reply that is a JSON array has `data.entries` ===
 * Array.prototype.entries -- a function -- so `data.entries ?? []` handed React
 * a function, React ran it as a state updater and the whole desk went down.
 * A body that is not an object is an unreadable reply, never a watchlist.
 */
export function readWatchlistEntries(data: unknown): WatchlistEntry[] | null {
  if (!isRecord(data)) return null;
  const raw = data.entries;
  if (!Array.isArray(raw)) return null;
  return raw.filter((entry): entry is WatchlistEntry => {
    if (!isRecord(entry) || typeof entry.symbol !== 'string' || !entry.symbol.trim()) return false;
    if (typeof entry.composite_score !== 'number' || !Number.isFinite(entry.composite_score)) return false;
    const pillars = entry.five_pillars;
    return isRecord(pillars) && Array.isArray(pillars.pillars);
  });
}

export function readWatchlistResponse(data: unknown): ParsedWatchlistResponse | null {
  const entries = readWatchlistEntries(data);
  if (!entries || !isRecord(data)) return null;
  const replay = readWatchlistReplay(data.replay);
  if (data.source === 'replay' && !replay) return null;
  return {
    entries,
    source: replay ? 'replay' : 'live',
    replay,
  };
}

export function useWatchlist(enabled: boolean): UseWatchlistReturn {
  const replayDesk = useSimReplayDesk();
  const playhead = useSimReplayPlayhead();
  const sessionDate = replayDesk ? (simClockResource.getSnapshot().data?.session_date ?? null) : null;
  const playheadMinute = replayDesk && playhead != null ? Math.floor(playhead / 60) : null;
  const scopeKey = replayDesk ? `replay:${sessionDate ?? ''}:${playhead ?? 'pending'}` : 'live';
  const clearKey = replayDesk ? `replay:${sessionDate ?? ''}:${playheadMinute ?? 'pending'}` : 'live';

  const [entries, setEntries] = useState<WatchlistEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [source, setSource] = useState<'live' | 'replay' | null>(null);
  const [replay, setReplay] = useState<WatchlistReplay | null>(null);

  const reqSeq = useRef(0);
  const prevClearKey = useRef(clearKey);
  const prevPlayhead = useRef<number | null>(playhead);

  useEffect(() => {
    if (!enabled) {
      publishWatchlistReplay(null);
      return;
    }
    let cancelled = false;
    const rewound =
      replayDesk
      && playhead != null
      && prevPlayhead.current != null
      && playhead < prevPlayhead.current;
    const shouldClear = prevClearKey.current !== clearKey || rewound;
    prevClearKey.current = clearKey;
    prevPlayhead.current = playhead;

    if (shouldClear) {
      setEntries([]);
      setReplay(null);
      setSource(null);
      setError(null);
      setLoading(true);
      publishWatchlistReplay(null);
    }

    async function poll() {
      const myReq = ++reqSeq.current;
      try {
        const res = await fetch(`${API}/watchlist`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const parsed = readWatchlistResponse(await res.json());
        if (!parsed) throw new Error(WATCHLIST_UNREADABLE);
        if (cancelled || myReq !== reqSeq.current) return;
        if (replayDesk && parsed.source !== 'replay') return;
        if (replayDesk && sessionDate && parsed.replay?.session_date && parsed.replay.session_date !== sessionDate) {
          return;
        }
        setEntries(parsed.entries);
        setSource(parsed.source);
        setReplay(parsed.replay);
        setError(null);
        publishWatchlistReplay(parsed.replay);
      } catch (err) {
        if (cancelled || myReq !== reqSeq.current) return;
        setEntries([]);
        setSource(null);
        setReplay(null);
        publishWatchlistReplay(null);
        setError(err instanceof Error ? err.message : 'Failed to load watchlist');
      } finally {
        if (!cancelled && myReq === reqSeq.current) setLoading(false);
      }
    }

    void poll();
    const interval = setInterval(() => void poll(), WATCHLIST_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [enabled, scopeKey, clearKey, replayDesk, playhead, sessionDate]);

  return { entries, loading, error, source, replay };
}
