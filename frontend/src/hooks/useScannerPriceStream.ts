/** Live IBKR scanner table prices / roster via /ws/scanner (ADR 008). */
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
  // Large Cap swing table only (ADR 014) — undefined on every other table's patch.
  rvol?: number | null;
  atr_expansion?: number | null;
  change_5d_pct?: number | null;
  change_20d_pct?: number | null;
  high_20d?: number | null;
  low_20d?: number | null;
  days_to_earnings?: number | null;
  market_cap?: number | null;
  float?: number | null;
};

export type ScannerTableMeta = {
  state: string;
  session_key: string;
  revision: number;
  roster_ts: number;
  quote_ts: number;
  frozen_at: number;
  source: string;
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

export type ScannerRosterHandlers = {
  onPatch: (rows: ScannerPricePatchRow[], ts: number, table?: string | null) => void;
  onRosterReplace?: (table: string, rows: unknown[], meta: ScannerTableMeta) => void;
  onTableState?: (table: string, meta: ScannerTableMeta) => void;
};

type Props = {
  enabled: boolean;
  /**
   * Every scanner table currently on screen (main tab + scanner dock) — sent
   * as set_active_tab so the backend streams L1 for all of them. A single tab
   * could not express "main = Gappers (frozen) + dock = Gainers (live)", which
   * left the visible Gainers column with no price_patch at all.
   */
  activeTabs?: readonly string[];
} & ScannerRosterHandlers;

const EMPTY_FLASH: Record<string, 'up' | 'down'> = {};
const SCANNER_TABS = new Set(['gappers', 'gainers', 'losers', 'afterhours', 'large_cap']);

/** Keep only real scanner tables, deduped — alert-only tabs contribute none. */
export function tabHints(tabs: readonly (string | null | undefined)[]): string[] {
  const out: string[] = [];
  for (const raw of tabs) {
    const t = (raw || '').toLowerCase();
    if (!SCANNER_TABS.has(t) || out.includes(t)) continue;
    out.push(t);
  }
  return out;
}

export function useScannerPriceStream({
  enabled,
  activeTabs,
  onPatch,
  onRosterReplace,
  onTableState,
}: Props): ScannerPriceFreshness {
  const [lastPriceTs, setLastPriceTs] = useState(0);
  const [heartbeatStale, setHeartbeatStale] = useState(false);
  const [flashSymbols, setFlashSymbols] = useState<Record<string, 'up' | 'down'>>(EMPTY_FLASH);
  const [rowQuoteTs, setRowQuoteTs] = useState<Record<string, number>>({});
  const [subscriptionError, setSubscriptionError] = useState<string | null>(null);
  const [nowTick, setNowTick] = useState(() => Date.now() / 1000);
  const onPatchRef = useRef(onPatch);
  onPatchRef.current = onPatch;
  const onRosterRef = useRef(onRosterReplace);
  onRosterRef.current = onRosterReplace;
  const onStateRef = useRef(onTableState);
  onStateRef.current = onTableState;
  const prevPricesRef = useRef<Record<string, number>>({});
  const wsRef = useRef<WebSocket | null>(null);
  const tabsKey = tabHints(activeTabs ?? []).join(',');
  const activeTabsRef = useRef(tabsKey);
  activeTabsRef.current = tabsKey;
  const tableRevRef = useRef<Record<string, number>>({});

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
      const tabs = activeTabsRef.current ? activeTabsRef.current.split(',') : [];
      socket.send(JSON.stringify({
        type: 'set_active_tab',
        tabs,
        tab: tabs[0] ?? 'none',
      }));
    }

    function applyMeta(table: string, meta: ScannerTableMeta): boolean {
      const prev = tableRevRef.current[table] ?? -1;
      if (typeof meta.revision === 'number' && meta.revision < prev) return false;
      tableRevRef.current[table] = meta.revision ?? prev;
      return true;
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
          if (msg.type === 'subscribed' && msg.tables && typeof msg.tables === 'object') {
            for (const [table, payload] of Object.entries(
              msg.tables as Record<string, { rows?: unknown[]; meta?: ScannerTableMeta }>,
            )) {
              const meta = payload.meta;
              if (!meta || !applyMeta(table, meta)) continue;
              onRosterRef.current?.(table, payload.rows ?? [], meta);
            }
          } else if (msg.type === 'roster_replace' && typeof msg.table === 'string') {
            const meta = msg.meta as ScannerTableMeta;
            if (!meta || !applyMeta(msg.table, meta)) return;
            onRosterRef.current?.(msg.table, msg.rows ?? [], meta);
          } else if (msg.type === 'table_state' && typeof msg.table === 'string') {
            const meta = msg.meta as ScannerTableMeta;
            if (!meta || !applyMeta(msg.table, meta)) return;
            onStateRef.current?.(msg.table, meta);
          } else if (msg.type === 'price_patch' && Array.isArray(msg.rows)) {
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
            const table = typeof msg.table === 'string' ? msg.table : null;
            onPatchRef.current(msg.rows, ts, table);
          } else if (msg.type === 'price_heartbeat') {
            if (msg.stale) setHeartbeatStale(true);
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

  useEffect(() => {
    if (!enabled) return;
    const socket = wsRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    const tabs = tabsKey ? tabsKey.split(',') : [];
    socket.send(JSON.stringify({
      type: 'set_active_tab',
      tabs,
      tab: tabs[0] ?? 'none',
    }));
  }, [enabled, tabsKey]);

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
      // Large Cap swing table only (ADR 014) — no-ops on every other table's patch.
      ...(p.rvol !== undefined ? { rvol: p.rvol } : {}),
      ...(p.atr_expansion !== undefined ? { atr_expansion: p.atr_expansion } : {}),
      ...(p.change_5d_pct !== undefined ? { change_5d_pct: p.change_5d_pct } : {}),
      ...(p.change_20d_pct !== undefined ? { change_20d_pct: p.change_20d_pct } : {}),
      ...(p.high_20d !== undefined ? { high_20d: p.high_20d } : {}),
      ...(p.low_20d !== undefined ? { low_20d: p.low_20d } : {}),
      ...(p.days_to_earnings !== undefined ? { days_to_earnings: p.days_to_earnings } : {}),
      ...(p.market_cap !== undefined ? { market_cap: p.market_cap } : {}),
      ...(p.float !== undefined ? { float: p.float } : {}),
    };
  });
  return changed ? next : rows;
}

/** Human label for a frozen scanner table. */
export function frozenTableLabel(meta: ScannerTableMeta | null | undefined): string | null {
  if (!meta || meta.state !== 'frozen' || !meta.frozen_at) return null;
  const d = new Date(meta.frozen_at * 1000);
  const hh = d.toLocaleTimeString('en-US', {
    timeZone: 'America/New_York',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
  return `Frozen at ${hh} ET`;
}
