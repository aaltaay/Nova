import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { WS_BASE_URL } from '../constants';
import { upsertTapePrint10SecBar } from '../chart/barsStore';
import { SAMPLE_LIVE_FEED_ABSENT } from '../sample_data/sampleCopy';
import { onSampleDesk } from '../sample_data/sampleOrderGuard';
import { createRafCoalesce } from '../utils/rafCoalesce';
import { documentVisible, LentLine } from './lentLine';
import {
  appendTapePrint,
  emptyTapeState,
  parseTapeSilence,
  tapeMessageAllowed,
  tapeSymbolKey,
  type TapePrint,
  type TapeSilence,
  type TapeState,
} from './tapeFeed';
import { countSocketMessage, frameBytes } from '../perf/perfCounters';

export type { TapePrint, TapeState, TapeSide } from './tapeFeed';

/** One print as the socket sends it: a `print` frame, or an item of a `prints` frame (ADR 045). */
interface TapeWirePrint {
  symbol?: string;
  time: string;
  price: number;
  size: number;
  exchange?: string;
  conditions?: string;
  side?: TapePrint['side'];
  bid?: number | null;
  ask?: number | null;
  unreported?: boolean;
  sets_price?: boolean;
  exchange_ts?: number | null;
}

export interface TapeOptions {
  /**
   * A Trader tab's Time & Sales: its socket says so (`tab=1`), so the backend may lend its AllLast
   * line with the tab's Level 2 line while no visible window shows the tab (ADR 044 decision 6:
   * IBKR counts tick-by-tick lines like depth lines). Any Time & Sales says whether it is in front
   * (`front=1`), which recalls a loan of its line.
   */
  traderTab?: boolean;
}

/**
 * Opens /ws/ibkr/tape/{symbol}, receives AllLast tick-by-tick prints.
 * Reconnects on disconnect. Clears prints on symbol change.
 *
 * Symbol gate: msg.symbol must match the hook's current symbol -- same
 * class of guard as useIbkrDepth to prevent cross-symbol bleed.
 *
 * Prints always land on the ordered ring. React state flushes once per
 * animation frame while ``uiActive``. Hidden live tabs keep the socket and
 * ring (and 10Sec upsert); they do not commit tape UI until shown again.
 *
 * A lent line (ADR 044 decision 6): the backend sends `{type: "lent", ...}` and closes. The ring
 * is cleared (the tape is no longer live, and a gap would not show), the pane says whose setup took
 * it, and the hook never reconnects by its backoff (LentLine): it reconnects when the shared lines
 * poll finds the loan ended, or at once when this Time & Sales comes to the front -- the same
 * moment as the tab's Level 2.
 *
 * A live line with no print for a while (#722): each idle `ping` carries the backend's reading
 * (`silence`: halted, silent or quiet), and any print clears it.
 */
export function useIbkrTape(symbol: string | null, uiActive = true, options: TapeOptions = {}): TapeState {
  const traderTab = options.traderTab === true;
  const [state, setState] = useState<TapeState>(emptyTapeState);
  const wsRef = useRef<WebSocket | null>(null);
  const backoffRef = useRef(1000);
  const mountedRef = useRef(true);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const printsRef = useRef<TapePrint[]>([]);
  const uiActiveRef = useRef(uiActive);
  const connectedRef = useRef(false);
  const errorRef = useRef<string | null>(null);
  // When the backend asks IBKR again for a refused line (#698); null when it is not retrying.
  const retryAtRef = useRef<number | null>(null);
  // This symbol's line while it may be lent; set by the socket effect.
  const lineRef = useRef<LentLine | null>(null);
  // The backend's word on a line with no print for a while (#722); null while it prints.
  const silenceRef = useRef<TapeSilence | null>(null);

  useEffect(() => {
    uiActiveRef.current = uiActive;
    if (uiActive) lineRef.current?.wake();     // shown: a lent line is taken back now
  }, [uiActive]);


  const commitUi = () => {
    if (!mountedRef.current) return;
    setState({
      prints: printsRef.current,
      connected: connectedRef.current,
      error: errorRef.current,
      lent: lineRef.current?.lent ?? null,
      retryAt: retryAtRef.current,
      silence: silenceRef.current,
    });
  };

  const rafRef = useRef(createRafCoalesce(commitUi));

  useLayoutEffect(() => {
    if (!uiActive) return;
    rafRef.current.flushNow();
  }, [uiActive]);

  useEffect(() => {
    mountedRef.current = true;
    const symKey = tapeSymbolKey(symbol);
    const raf = rafRef.current;

    printsRef.current = [];
    connectedRef.current = false;
    errorRef.current = null;
    retryAtRef.current = null;
    lineRef.current = null;
    silenceRef.current = null;
    raf.cancel();
    setState(emptyTapeState());

    if (!symKey) {
      return;
    }

    // V4: the sample desk opens no live tape line -- a stated absence instead.
    if (onSampleDesk()) {
      errorRef.current = SAMPLE_LIVE_FEED_ABSENT;
      setState({ ...emptyTapeState(), error: SAMPLE_LIVE_FEED_ABSENT });
      return;
    }

    const inFront = () => uiActiveRef.current && documentVisible();
    const line = new LentLine(symKey, {
      inFront,
      // The loan ended, or this Time & Sales came to the front (its socket recalls the loan): ask now.
      reconnect: () => {
        backoffRef.current = 1000;
        connect();
      },
      changed: () => {
        if (uiActiveRef.current) commitUi();
      },
    });
    lineRef.current = line;

    function connect() {
      if (!mountedRef.current) return;
      const params = `?${traderTab ? 'tab=1&' : ''}front=${inFront() ? 1 : 0}`;
      const ws = new WebSocket(`${WS_BASE_URL}/ws/ibkr/tape/${symKey}${params}`);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current || ws !== wsRef.current) return;
        backoffRef.current = 1000;
      };

      ws.onmessage = (e) => {
        countSocketMessage('tape', frameBytes(e.data));
        if (!mountedRef.current || ws !== wsRef.current) return;
        try {
          const msg = JSON.parse(e.data as string);
          if (!tapeMessageAllowed(msg.symbol, symKey!)) return;
          if (msg.type === 'subscribed' || msg.type === 'print' || msg.type === 'prints' || msg.type === 'error') {
            line.answered();
          }

          if (msg.type !== 'ping') silenceRef.current = null;  // a print, or any word on the line, ends a silence

          if (msg.type === 'ping') {
            const next = parseTapeSilence(msg.silence);
            const prev = silenceRef.current;
            if (next?.state !== prev?.state || next?.since !== prev?.since || next?.text !== prev?.text) {
              silenceRef.current = next;
              if (uiActiveRef.current) commitUi();
            }
            return;
          }

          if (msg.type === 'scrub_reset') {
            printsRef.current = [];
            connectedRef.current = true;
            errorRef.current = null;
            if (uiActiveRef.current) commitUi();
            return;
          }

          if (msg.type === 'subscribed') {
            connectedRef.current = true;
            errorRef.current = null;
            retryAtRef.current = null;
            if (uiActiveRef.current) commitUi();
          } else if (msg.type === 'print' || msg.type === 'prints') {
            // A print means the line works: an error from before it is stale (#698).
            if (errorRef.current != null || !connectedRef.current) {
              connectedRef.current = true;
              errorRef.current = null;
              retryAtRef.current = null;
            }
            // ADR 045: prints waiting together arrive as one `prints` frame, oldest first.
            const items: TapeWirePrint[] = msg.type === 'prints' ? (Array.isArray(msg.items) ? msg.items : []) : [msg];
            for (const item of items) {
              const print: TapePrint = {
                symbol: item.symbol ?? msg.symbol,
                time: item.time,
                price: item.price,
                size: item.size,
                exchange: item.exchange ?? '',
                conditions: item.conditions ?? '',
                side: item.side,
                bid: item.bid ?? null,
                ask: item.ask ?? null,
                unreported: item.unreported === true,
                // Older backends send no verdict: treat the print as a price, as before.
                setsPrice: item.sets_price !== false,
              };
              printsRef.current = appendTapePrint(printsRef.current, print);
              upsertTapePrint10SecBar(symKey!, {
                time: print.time,
                price: print.price,
                size: print.size,
                setsPrice: print.setsPrice,
                // IBKR's own second: the 10-second candle's key, as in IBKR's history (#721).
                exchangeTs: typeof item.exchange_ts === 'number' ? item.exchange_ts : null,
              });
            }
            if (uiActiveRef.current) raf.schedule();
          } else if (msg.type === 'lent') {
            // Lent to a setup with the tab's Level 2 (ADR 044): this tape is no longer live; the socket closes next.
            line.lend(msg);
            printsRef.current = [];
            connectedRef.current = false;
            errorRef.current = null;
            retryAtRef.current = null;
            raf.cancel();
            if (uiActiveRef.current) commitUi();
          } else if (msg.type === 'error') {
            connectedRef.current = false;
            errorRef.current = typeof msg.message === 'string' ? msg.message : 'Tape error';
            retryAtRef.current = typeof msg.retry_at === 'number' && Number.isFinite(msg.retry_at) ? msg.retry_at : null;
            if (uiActiveRef.current) commitUi();
          }
        } catch {
          // ignore parse errors
        }
      };

      ws.onclose = () => {
        if (!mountedRef.current || ws !== wsRef.current) return;
        connectedRef.current = false;
        silenceRef.current = null;
        // Lent: never by the backoff -- when the loan ends (the poll), or now if this pane is in front.
        const lent = line.closed();
        if (uiActiveRef.current) commitUi();
        if (lent) return;
        const delay = backoffRef.current;
        backoffRef.current = Math.min(delay * 2, 30_000);
        reconnectTimerRef.current = setTimeout(connect, delay);
      };
    }

    connect();

    return () => {
      mountedRef.current = false;
      raf.cancel();
      line.dispose();
      if (lineRef.current === line) lineRef.current = null;
      if (reconnectTimerRef.current != null) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      const ws = wsRef.current;
      wsRef.current = null;
      ws?.close();
    };
  }, [symbol, traderTab]);

  return state;
}
