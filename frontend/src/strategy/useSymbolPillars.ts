/**
 * The Five Pillars for the quote panel's symbol, ranked on the watchlist or
 * not (operator ask, 2026-09-23). A ranked symbol reads its entry from the
 * watchlist poll the desk already runs; any other symbol asks
 * GET /api/strategy/watchlist/{symbol}, which grades its own scanner row or
 * its live quote, polled while the symbol is on screen. On a Sim replay desk the
 * backend grades the replayed day's own board row at the playhead (`replay`), or
 * says why there is none -- never today's (operator report, 2026-10-12). The
 * sample desk sends nothing (V4) and shows only its own watchlist.
 */
import { useEffect, useState } from 'react';
import { novaFetch } from '../api/novaFetch';
import { API_URL } from '../constantGroups/chart_api';
import { symbolPillarsPath, WATCHLIST_STRIP_POLL_MS } from '../constantGroups/watchlist_strip';
import { onSampleDesk } from '../sample_data/sampleOrderGuard';
import { readWatchlistEntries } from './useWatchlist';
import type { WatchlistEntry } from './types';

/** What a replay desk's grade came from (`replay` on the route), or why there is none (`absent`). */
export interface PillarsReplay {
  session_date: string;
  /** The playhead, epoch seconds. */
  at: number;
  /** The board minute read, epoch seconds; null with no board. */
  minute_ts: number | null;
  /** `recorded` | `reconstructed`. */
  board_source: string | null;
  board: string | null;
  board_rank: number | null;
  /** Why there is no grade: the board's gap reason, or `not_on_board`; null when graded. */
  absent: string | null;
}

export interface SymbolPillars {
  entry: WatchlistEntry | null;
  /** 'watchlist' for a ranked entry; else the board the grade came from, 'quote', or 'replay'. */
  source: string | null;
  rank: number | null;
  /** Set on a Sim replay desk; `entry` is then the replayed day's, or null with `replay.absent`. */
  replay: PillarsReplay | null;
  error: string | null;
  loading: boolean;
}

const NONE: SymbolPillars = { entry: null, source: null, rank: null, replay: null, error: null, loading: false };

const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const str = (v: unknown): string | null => (typeof v === 'string' && v ? v : null);

export function readPillarsReplay(raw: unknown): PillarsReplay | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
  const r = raw as Record<string, unknown>;
  const at = num(r.at);
  if (typeof r.session_date !== 'string' || at == null) return null;
  return {
    session_date: r.session_date, at, minute_ts: num(r.minute_ts), board_source: str(r.board_source),
    board: str(r.board), board_rank: num(r.board_rank), absent: str(r.absent),
  };
}

/** `{symbol, source, rank, entry, replay}` -> the grade, or null when the body is not one. */
export function readSymbolPillars(body: unknown): Omit<SymbolPillars, 'error' | 'loading'> | null {
  if (!body || typeof body !== 'object' || Array.isArray(body)) return null;
  const raw = body as { source?: unknown; rank?: unknown; entry?: unknown; replay?: unknown };
  const [entry] = readWatchlistEntries({ entries: [raw.entry] }) ?? [];
  const replay = readPillarsReplay(raw.replay);
  // A replayed symbol with no row at the playhead has no entry, and says why.
  if (!entry && !(replay && replay.absent)) return null;
  return {
    entry: entry ?? null,
    source: typeof raw.source === 'string' ? raw.source : null,
    rank: typeof raw.rank === 'number' && Number.isFinite(raw.rank) ? raw.rank : null,
    replay,
  };
}

export function useSymbolPillars(symbol: string | null | undefined, ranked: WatchlistEntry | null, rank: number | null = null): SymbolPillars {
  const sym = (symbol ?? '').trim().toUpperCase();
  const fetchIt = Boolean(sym) && !ranked && !onSampleDesk();
  const [state, setState] = useState<SymbolPillars & { symbol: string }>({ ...NONE, symbol: '' });

  useEffect(() => {
    if (!fetchIt) return undefined;
    let cancelled = false;
    setState(prev => (prev.symbol === sym ? prev : { ...NONE, symbol: sym, loading: true }));
    async function poll() {
      try {
        const res = await novaFetch(`${API_URL}${symbolPillarsPath(sym)}`);
        if (!res.ok) throw new Error(`Five Pillars: HTTP ${res.status}`);
        const read = readSymbolPillars(await res.json());
        if (!read) throw new Error('Five Pillars: unreadable response');
        if (!cancelled) setState({ ...read, error: null, loading: false, symbol: sym });
      } catch (err) {
        if (!cancelled) {
          setState(prev => ({ ...(prev.symbol === sym ? prev : NONE), symbol: sym, loading: false,
            error: err instanceof Error ? err.message : String(err) }));
        }
      }
    }
    void poll();
    const id = window.setInterval(() => void poll(), WATCHLIST_STRIP_POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [fetchIt, sym]);

  if (ranked) return { entry: ranked, source: 'watchlist', rank, replay: null, error: null, loading: false };
  if (!fetchIt || state.symbol !== sym) return { ...NONE, loading: fetchIt };
  return {
    entry: state.entry, source: state.source, rank: state.rank, replay: state.replay, error: state.error,
    loading: state.loading,
  };
}
