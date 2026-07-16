/** Live IBKR scanner table prices via /ws/scanner (bounded L1 streams). */
import { useEffect, useRef, useState } from 'react';
import {
  IBKR_L1_ROW_STALE_SEC,
  SCANNER_PRICE_STALE_SEC,
  WS_BASE_URL,
} from '../constants';

export type ScannerPricePatchRow = {
  symbol: string;
  price?: number | null;
  change_pct?: number | null;
  change_abs?: number | null;
  volume?: number | null;
  gap_percent?: number | null;
  quote_ts?: number | null;
};

export type ScannerPriceFreshness = {
  /** Unix seconds of last successful price_patch. */
  lastPriceTs: number;
  /** True when last patch is too old or subscription is incomplete. */
  pricesStale: boolean;
  /** Symbols whose price changed on the latest patch (for flash). */
  flashSymbols: Record<string, 'up' | 'down'>;
  /** Per-symbol last IB quote timestamp (unix seconds). */
  rowQuoteTs: Record<string, number>;
  /** Subscription / capacity error from backend, if any. */
  subscriptionError: string | null;
};

type Props = {
  enabled: boolean;
  /** Active scanner tab — sent as set_active_tab for L1 budget. */
  activeTab?: string;
  onPatch: (rows: ScannerPricePatchRow[], ts: number) => void;
};

const EMPTY_FLASH: Record<string, 'up' | 'down'> = {};
const SCANNER_TABS = new Set(['gappers', 'gainers', 'losers', 'afterhours']);

function tabHint(tab: string | undefined): string {
  const t = (tab || 'none').toLowerCase();
  if (SCANNER_TABS.has(t)) return t;
  return 'none';
}

export function useScannerPriceStream({
  enabled,
  activeTab,
  onPatch,
}: Props): ScannerPriceFreshness {
  const [lastPriceTs, setLastPriceTs] = useState(0);
  const [heartbeatStale, setHeartbeatStale] = useState(false);
  const [flashSymbols, setFlashSymbols] = useState<Record<string, 'up' | 'down'>>(EMPTY_FLASH);
  const [rowQuoteTs, setRowQuoteTs] = useState<Record<string, number>>({});
  const [subscriptionError, setSubscriptionError] = useState<string | null>(null);
  const [nowTick, setNowTick] = useState(() => Date.now() / 1000);
  const onPatchRef = useRef(onPatch);
  onPatchRef.current = onPatch;
  const prevPricesRef = useRef<Record<string, number>>({});
  const wsRef = useRef<WebSocket | null>(null);
  const activeTabRef = useRef(activeTab);
  activeTabRef.current = activeTab;

  useEffect(() => {
    const id = setInterval(() => setNowTick(Date.now() / 1000), 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (!enabled) {
      setHeartbeatStale(false);
      setFlashSymbols(EMPTY_FLASH);
      setSubscriptionError(null);
      return;
    }

    let cancelled = false;
    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let backoff = 1000;

    function sendTabHint(socket: WebSocket) {
      if (socket.readyState !== WebSocket.OPEN) return;
      socket.send(JSON.stringify({
        type: 'set_active_tab',
        tab: tabHint(activeTabRef.current),
      }));
    }

    function connect() {
      if (cancelled) return;
      ws = new WebSocket(`${WS_BASE_URL}/ws/scanner`);
      wsRef.current = ws;

      ws.onopen = () => {
        backoff = 1000;
        sendTabHint(ws!);
      };

      ws.onmessage = (e) => {
        if (cancelled) return;
        try {
          const msg = JSON.parse(e.data as string);
          if (msg.type === 'price_patch' && Array.isArray(msg.rows)) {
            const ts = typeof msg.ts === 'number' ? msg.ts : Date.now() / 1000;
            const flash: Record<string, 'up' | 'down'> = {};
            const quoteUpdates: Record<string, number> = {};
            for (const row of msg.rows as ScannerPricePatchRow[]) {
              const sym = row.symbol?.toUpperCase();
              if (!sym || row.price == null) continue;
              const prev = prevPricesRef.current[sym];
              if (prev != null && row.price !== prev) {
                flash[sym] = row.price > prev ? 'up' : 'down';
              }
              prevPricesRef.current[sym] = row.price;
              const qts = typeof row.quote_ts === 'number' ? row.quote_ts : ts;
              quoteUpdates[sym] = qts;
            }
            setLastPriceTs(ts);
            setHeartbeatStale(false);
            setFlashSymbols(flash);
            if (Object.keys(quoteUpdates).length) {
              setRowQuoteTs(prev => ({ ...prev, ...quoteUpdates }));
            }
            const subErr = msg.subscription?.error;
            setSubscriptionError(typeof subErr === 'string' ? subErr : null);
            onPatchRef.current(msg.rows, ts);
          } else if (msg.type === 'price_heartbeat') {
            if (msg.stale) setHeartbeatStale(true);
          } else if (msg.type === 'subscription_state') {
            // ack only — state is also on price_patch
          }
        } catch {
          // ignore parse errors
        }
      };

      ws.onclose = () => {
        if (cancelled) return;
        setHeartbeatStale(true);
        wsRef.current = null;
        reconnectTimer = setTimeout(connect, backoff);
        backoff = Math.min(backoff * 2, 15_000);
      };
    }

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer != null) clearTimeout(reconnectTimer);
      ws?.close();
      wsRef.current = null;
    };
  }, [enabled]);

  // Resend tab hint when the user switches scanner tabs (same WS).
  useEffect(() => {
    if (!enabled) return;
    const socket = wsRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    socket.send(JSON.stringify({
      type: 'set_active_tab',
      tab: tabHint(activeTab),
    }));
  }, [enabled, activeTab]);

  const age = lastPriceTs > 0 ? nowTick - lastPriceTs : Infinity;
  const pricesStale =
    lastPriceTs > 0
      ? age > SCANNER_PRICE_STALE_SEC || Boolean(subscriptionError)
      : heartbeatStale;

  return {
    lastPriceTs,
    pricesStale,
    flashSymbols,
    rowQuoteTs,
    subscriptionError,
  };
}

/** True when this row's last IB quote is older than the L1 row-stale threshold. */
export function isRowQuoteStale(
  symbol: string,
  rowQuoteTs: Record<string, number>,
  nowSec: number,
  globalStale: boolean,
): boolean {
  const ts = rowQuoteTs[symbol.toUpperCase()];
  if (ts == null) return globalStale;
  return nowSec - ts > IBKR_L1_ROW_STALE_SEC;
}

/** Merge a price patch into an existing scanner row list (by symbol). */
export function applyScannerPricePatch<T extends { symbol: string }>(
  rows: T[],
  patch: ScannerPricePatchRow[],
): T[] {
  if (!rows.length || !patch.length) return rows;
  const bySym = new Map(patch.map(r => [r.symbol.toUpperCase(), r]));
  let changed = false;
  const next = rows.map(row => {
    const p = bySym.get(row.symbol.toUpperCase());
    if (!p) return row;
    changed = true;
    return {
      ...row,
      ...(p.price != null ? { price: p.price, current_price: p.price } : {}),
      ...(p.change_pct != null ? { change_pct: p.change_pct } : {}),
      ...(p.change_abs != null ? { change_abs: p.change_abs } : {}),
      ...(p.volume != null ? { volume: p.volume } : {}),
      ...(p.gap_percent != null ? { gap_percent: p.gap_percent } : {}),
    };
  });
  return changed ? next : rows;
}
