/**
 * The ticker detail stream, one per symbol for the whole window: the Phase 1 fast snapshot, the Phase 2
 * slow enrich and every live trade (`/ws/ticker/{symbol}`, an HTTP seed when the socket is slow).
 *
 * It lives outside React (#707). As a hook's state it sat at the top of the Trader page, so every print
 * rendered the whole page -- the charts' frames, the stock read, the rail, the orders -- about 20 times a
 * second on a busy tape. Now a reader subscribes to the part it shows (`useTickerSelect`), a chart applies
 * prints to its series with no render at all, and two readers of one symbol share one socket. The socket
 * opens with the first reader and closes when the last one leaves (a reader that goes and comes back in
 * one React commit keeps it).
 */
import {
  API_BASE_URL,
  TICKER_WS_HTTP_SEED_MS,
  TICKER_WS_RECONNECT_CAP_MS,
  TICKER_WS_RECONNECT_MS,
  WS_BASE_URL,
} from '../constants';
import type { BarData, TickerDetail, TickerTradeUpdate } from '../types/ticker';
import { applyBarsPatch, parseBarsCoverage } from '../chart/barsStore';
import { tickerDetailFromHttp, tickerDetailFromWsInitial } from './tickerStreamHttp';
import { countSocketMessage, frameBytes } from '../perf/perfCounters';

const WS_URL = `${WS_BASE_URL}/ws`;

export type TickerStreamState = {
  detail: TickerDetail | null;
  loading: boolean;
  refreshing: boolean;
  fetchFailed: boolean;
  stale: boolean;
  disconnectedSince: number | null;
};

export const IDLE_TICKER: TickerStreamState = {
  detail: null,
  loading: false,
  refreshing: false,
  fetchFailed: false,
  stale: false,
  disconnectedSince: null,
};

/** The detail is `symbol`'s own (never the previous ticker's while the new one loads). */
export function tickerReady(state: TickerStreamState, symbol: string): boolean {
  const own = typeof state.detail?.symbol === 'string' ? state.detail.symbol : '';
  return own !== '' && own.toUpperCase() === symbol.trim().toUpperCase();
}

/** The last trade as a chart and the stock read take it, or null before `symbol`'s first one. */
export interface TickerLastTrade {
  price: number;
  timestamp: string | null;
  source?: 'stream' | 'snapshot' | 'sim';
  dayVolume: number | null;
}

export function tickerLastTrade(state: TickerStreamState, symbol: string): TickerLastTrade | null {
  if (!tickerReady(state, symbol)) return null;
  const latest = state.detail?.snapshot?.latest_trade;
  if (latest?.price == null) return null;
  return { price: latest.price, timestamp: latest.timestamp ?? null, source: latest.source, dayVolume: latest.day_volume ?? null };
}

/** A message that says the line is up: no longer stale, failed or disconnected. */
const LIVE: Partial<TickerStreamState> = { stale: false, disconnectedSince: null, fetchFailed: false };

interface Stream {
  state: TickerStreamState;
  listeners: Set<() => void>;
  close: (() => void) | null;
  closeTimer: ReturnType<typeof setTimeout> | null;
}

const streams = new Map<string, Stream>();

/** The symbol's state now; idle when nothing reads it. */
export function tickerState(symbol: string | null): TickerStreamState {
  return (symbol ? streams.get(symbol)?.state : undefined) ?? IDLE_TICKER;
}

function emit(s: Stream): void {
  for (const onChange of [...s.listeners]) onChange();
}

/** A trade folded into the detail, as the hook did: the day's bar, the prior close and the last trade. */
function withTrade(prev: TickerDetail, update: TickerTradeUpdate): TickerDetail {
  const newPrice = update.price;
  const prevDailyBar = prev.snapshot?.daily_bar ?? null;
  const newDailyBar: BarData | null = prevDailyBar
    ? { ...prevDailyBar, close: newPrice, volume: update.volume ?? prevDailyBar.volume }
    : {
        open: null,
        high: null,
        low: null,
        close: newPrice,
        volume: update.volume ?? null,
        trade_count: null,
        vwap: null,
        timestamp: null,
      };
  const nextPrevClose = update.prev_close ?? prev.snapshot?.prev_close ?? null;
  const newSnapshot = {
    ...prev.snapshot,
    daily_bar: newDailyBar,
    prev_close: nextPrevClose,
    session_close: update.prev_close != null ? update.prev_close : prev.snapshot?.session_close ?? null,
    latest_trade: {
      price: newPrice,
      size: update.size ?? prev.snapshot?.latest_trade?.size ?? null,
      timestamp: update.timestamp ?? prev.snapshot?.latest_trade?.timestamp ?? null,
      exchange: prev.snapshot?.latest_trade?.exchange ?? null,
      // Older backends send no source: treat as a print, as before.
      source: update.source ?? 'stream',
      day_volume: update.volume ?? null,
    },
  };
  const dailyVol = newDailyBar?.volume ?? null;
  const avgVol = prev.avg_volume;
  const relVol = dailyVol != null && avgVol != null && avgVol > 0
    ? Math.round((dailyVol / avgVol) * 100) / 100
    : prev.rel_volume;
  return { ...prev, snapshot: newSnapshot, rel_volume: relVol };
}

/** Open `symKey`'s line and keep `s.state` current; returns what closes it. */
function open(symKey: string, s: Stream): () => void {
  let cancelled = false;
  let initialReceived = false;
  let ws: WebSocket | null = null;
  let backoff = TICKER_WS_RECONNECT_MS;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  const set = (patch: Partial<TickerStreamState>) => {
    if (cancelled) return;
    s.state = { ...s.state, ...patch };
    emit(s);
  };
  /** The detail of this symbol, or null while another (or none) is held. */
  const ours = () => {
    const prev = s.state.detail;
    return prev && prev.symbol.toUpperCase() === symKey ? prev : null;
  };

  // Symbol gate: never keep the previous ticker's detail while the new one loads.
  set({ ...IDLE_TICKER, loading: true, refreshing: true });

  const seedCtl = new AbortController();
  const seedTimer = setTimeout(() => {
    if (cancelled || initialReceived) return;
    void fetch(`${API_BASE_URL}/api/ticker/${encodeURIComponent(symKey)}`, { signal: seedCtl.signal })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (cancelled || initialReceived) return;
        const seeded = tickerDetailFromHttp(data, symKey);
        if (!seeded) return;
        initialReceived = true;
        set({ ...LIVE, detail: seeded, loading: false, refreshing: false });
      })
      .catch(() => {
        /* WS may still deliver initial */
      });
  }, TICKER_WS_HTTP_SEED_MS);

  function onMessage(sock: WebSocket, data: unknown): void {
    countSocketMessage('ticker', frameBytes(data));
    if (cancelled || sock !== ws) return;
    try {
      const msg = JSON.parse(String(data));
      const msgSym = typeof msg.symbol === 'string' ? msg.symbol.toUpperCase() : null;
      if (msgSym != null && msgSym !== symKey) return;

      if (msg.type === 'initial') {
        const next = tickerDetailFromWsInitial(msg, symKey);
        if (!next) {
          set({ loading: false, refreshing: false, fetchFailed: true });
          return;
        }
        initialReceived = true;
        set({ ...LIVE, detail: next, loading: false, refreshing: false });
      } else if (msg.type === 'detail_update') {
        if (!initialReceived) return;
        const prev = ours();
        set(prev ? {
          ...LIVE,
          detail: {
            ...prev,
            news: msg.news ?? prev.news,
            fundamentals: msg.fundamentals ?? prev.fundamentals,
            avg_volume: msg.avg_volume ?? prev.avg_volume,
            rel_volume: msg.rel_volume ?? prev.rel_volume,
            rvol_5min: msg.rvol_5min ?? prev.rvol_5min,
            volume_in_5min: msg.volume_in_5min ?? prev.volume_in_5min,
            news_impact: msg.news_impact ?? prev.news_impact,
            listing: msg.listing ?? prev.listing,
            halt: msg.halt !== undefined ? msg.halt : prev.halt,
          },
        } : LIVE);
      } else if (msg.type === 'halt_update') {
        if (!initialReceived) return;
        const prev = ours();
        set(prev ? { ...LIVE, detail: { ...prev, halt: msg.halt ?? null } } : LIVE);
      } else if (msg.type === 'bars_patch') {
        const tf = typeof msg.timeframe === 'string' ? msg.timeframe : '';
        if (!tf || !Array.isArray(msg.bars)) return;
        applyBarsPatch(symKey, tf, msg.bars, parseBarsCoverage(msg.coverage));
      } else if (msg.type === 'trade_update') {
        if (!initialReceived) return;
        const prev = ours();
        set(prev ? { ...LIVE, detail: withTrade(prev, msg as TickerTradeUpdate) } : LIVE);
      }
    } catch {
      // ignore parse errors
    }
  }

  function connect(): void {
    if (cancelled) return;
    const sock = new WebSocket(`${WS_URL}/ticker/${symKey}`);
    ws = sock;
    sock.onopen = () => {
      if (sock === ws) backoff = TICKER_WS_RECONNECT_MS;
    };
    sock.onmessage = (e) => onMessage(sock, e.data);
    // Do not reconnect from onerror alone -- browsers fire it just before onclose.
    sock.onerror = () => {
      if (cancelled || sock !== ws) return;
      set({ loading: false, refreshing: false, ...(initialReceived ? {} : { fetchFailed: true }) });
    };
    sock.onclose = () => {
      if (cancelled || sock !== ws) return;
      set(initialReceived
        ? { loading: false, refreshing: false, stale: true, disconnectedSince: s.state.disconnectedSince ?? Date.now() }
        : { loading: false, refreshing: false, fetchFailed: true });
      const delay = backoff;
      backoff = Math.min(delay * 2, TICKER_WS_RECONNECT_CAP_MS);
      reconnectTimer = setTimeout(connect, delay);
    };
  }

  connect();

  return () => {
    cancelled = true;
    clearTimeout(seedTimer);
    seedCtl.abort();
    if (reconnectTimer != null) clearTimeout(reconnectTimer);
    const sock = ws;
    ws = null;
    sock?.close();
  };
}

/**
 * Read `symbol`'s stream from now on: `onChange` runs on every change. The first reader opens the line;
 * the returned function stops reading, and the line closes once no reader is left.
 */
export function subscribeTicker(symbol: string, onChange: () => void): () => void {
  let s = streams.get(symbol);
  if (!s) {
    s = { state: IDLE_TICKER, listeners: new Set(), close: null, closeTimer: null };
    streams.set(symbol, s);
  }
  const stream = s;
  if (stream.closeTimer != null) {
    clearTimeout(stream.closeTimer);
    stream.closeTimer = null;
  }
  stream.listeners.add(onChange);
  if (!stream.close) stream.close = open(symbol, stream);
  let done = false;
  return () => {
    if (done) return;
    done = true;
    stream.listeners.delete(onChange);
    if (stream.listeners.size > 0 || stream.closeTimer != null) return;
    // A reader that leaves and comes back in one commit (a remount) keeps the line.
    stream.closeTimer = setTimeout(() => {
      stream.closeTimer = null;
      if (stream.listeners.size > 0) return;
      stream.close?.();
      stream.close = null;
      if (streams.get(symbol) === stream) streams.delete(symbol);
    }, 0);
  };
}

/** Test helper: close every line and forget every symbol. */
export function resetTickerStreamsForTests(): void {
  for (const s of streams.values()) {
    if (s.closeTimer != null) clearTimeout(s.closeTimer);
    s.close?.();
  }
  streams.clear();
}
