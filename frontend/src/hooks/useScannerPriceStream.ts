/** Live IBKR scanner table price patches via /ws/scanner (1Hz snapshots). */
import { useEffect, useRef, useState } from 'react';
import { SCANNER_PRICE_STALE_SEC, WS_BASE_URL } from '../constants';

export type ScannerPricePatchRow = {
  symbol: string;
  price?: number | null;
  change_pct?: number | null;
  change_abs?: number | null;
  volume?: number | null;
  gap_percent?: number | null;
};

export type ScannerPriceFreshness = {
  /** Unix seconds of last successful price_patch. */
  lastPriceTs: number;
  /** True when heartbeat says stale or last patch is too old. */
  pricesStale: boolean;
  /** Symbols whose price changed on the latest patch (for flash). */
  flashSymbols: Record<string, 'up' | 'down'>;
};

type Props = {
  enabled: boolean;
  onPatch: (rows: ScannerPricePatchRow[], ts: number) => void;
};

const EMPTY_FLASH: Record<string, 'up' | 'down'> = {};

export function useScannerPriceStream({ enabled, onPatch }: Props): ScannerPriceFreshness {
  const [lastPriceTs, setLastPriceTs] = useState(0);
  const [heartbeatStale, setHeartbeatStale] = useState(false);
  const [flashSymbols, setFlashSymbols] = useState<Record<string, 'up' | 'down'>>(EMPTY_FLASH);
  const [nowTick, setNowTick] = useState(() => Date.now() / 1000);
  const onPatchRef = useRef(onPatch);
  onPatchRef.current = onPatch;
  const prevPricesRef = useRef<Record<string, number>>({});

  useEffect(() => {
    const id = setInterval(() => setNowTick(Date.now() / 1000), 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (!enabled) {
      setHeartbeatStale(false);
      setFlashSymbols(EMPTY_FLASH);
      return;
    }

    let cancelled = false;
    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let backoff = 1000;

    function connect() {
      if (cancelled) return;
      ws = new WebSocket(`${WS_BASE_URL}/ws/scanner`);

      ws.onopen = () => {
        backoff = 1000;
      };

      ws.onmessage = (e) => {
        if (cancelled) return;
        try {
          const msg = JSON.parse(e.data as string);
          if (msg.type === 'price_patch' && Array.isArray(msg.rows)) {
            const ts = typeof msg.ts === 'number' ? msg.ts : Date.now() / 1000;
            const flash: Record<string, 'up' | 'down'> = {};
            for (const row of msg.rows as ScannerPricePatchRow[]) {
              const sym = row.symbol?.toUpperCase();
              if (!sym || row.price == null) continue;
              const prev = prevPricesRef.current[sym];
              if (prev != null && row.price !== prev) {
                flash[sym] = row.price > prev ? 'up' : 'down';
              }
              prevPricesRef.current[sym] = row.price;
            }
            setLastPriceTs(ts);
            setHeartbeatStale(false);
            setFlashSymbols(flash);
            onPatchRef.current(msg.rows, ts);
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
        reconnectTimer = setTimeout(connect, backoff);
        backoff = Math.min(backoff * 2, 15_000);
      };
    }

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer != null) clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, [enabled]);

  const age = lastPriceTs > 0 ? nowTick - lastPriceTs : Infinity;
  // Heartbeat stale alone is not enough — mid-batch skip-if-busy fires every
  // second while a healthy snapshot runs for several seconds. Only paint stale
  // when we have not had a successful price_patch within SCANNER_PRICE_STALE_SEC
  // (or never received one and the socket is complaining).
  const pricesStale =
    lastPriceTs > 0
      ? age > SCANNER_PRICE_STALE_SEC
      : heartbeatStale;

  return { lastPriceTs, pricesStale, flashSymbols };
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
