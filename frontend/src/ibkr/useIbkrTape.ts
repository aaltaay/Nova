import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { WS_BASE_URL } from '../constants';
import { upsertTapePrint10SecBar } from '../chart/barsStore';
import { createRafCoalesce } from '../utils/rafCoalesce';
import {
  appendTapePrint,
  emptyTapeState,
  tapeMessageAllowed,
  tapeSymbolKey,
  type TapePrint,
  type TapeState,
} from './tapeFeed';

export type { TapePrint, TapeState, TapeSide } from './tapeFeed';

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
 */
export function useIbkrTape(symbol: string | null, uiActive = true): TapeState {
  const [state, setState] = useState<TapeState>(emptyTapeState);
  const wsRef = useRef<WebSocket | null>(null);
  const backoffRef = useRef(1000);
  const mountedRef = useRef(true);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const printsRef = useRef<TapePrint[]>([]);
  const uiActiveRef = useRef(uiActive);
  const connectedRef = useRef(false);
  const errorRef = useRef<string | null>(null);

  useEffect(() => {
    uiActiveRef.current = uiActive;
  }, [uiActive]);

  const commitUi = () => {
    if (!mountedRef.current) return;
    setState({
      prints: printsRef.current,
      connected: connectedRef.current,
      error: errorRef.current,
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

    if (!symKey) {
      printsRef.current = [];
      connectedRef.current = false;
      errorRef.current = null;
      raf.cancel();
      setState(emptyTapeState());
      return;
    }

    printsRef.current = [];
    connectedRef.current = false;
    errorRef.current = null;
    raf.cancel();
    setState(emptyTapeState());

    function connect() {
      if (!mountedRef.current) return;
      const ws = new WebSocket(`${WS_BASE_URL}/ws/ibkr/tape/${symKey}`);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current || ws !== wsRef.current) return;
        backoffRef.current = 1000;
      };

      ws.onmessage = (e) => {
        if (!mountedRef.current || ws !== wsRef.current) return;
        try {
          const msg = JSON.parse(e.data as string);
          if (!tapeMessageAllowed(msg.symbol, symKey!)) return;

          if (msg.type === 'subscribed') {
            connectedRef.current = true;
            errorRef.current = null;
            if (uiActiveRef.current) {
              setState(s => ({
                ...s,
                connected: true,
                error: null,
                prints: printsRef.current,
              }));
            }
          } else if (msg.type === 'print') {
            const print: TapePrint = {
              symbol: msg.symbol,
              time: msg.time,
              price: msg.price,
              size: msg.size,
              exchange: msg.exchange ?? '',
              conditions: msg.conditions ?? '',
              side: msg.side,
              bid: msg.bid ?? null,
              ask: msg.ask ?? null,
            };
            printsRef.current = appendTapePrint(printsRef.current, print);
            upsertTapePrint10SecBar(symKey!, {
              time: print.time,
              price: print.price,
              size: print.size,
            });
            if (uiActiveRef.current) raf.schedule();
          } else if (msg.type === 'error') {
            connectedRef.current = false;
            errorRef.current = typeof msg.message === 'string' ? msg.message : 'Tape error';
            if (uiActiveRef.current) {
              setState(s => ({
                ...s,
                connected: false,
                error: errorRef.current,
                prints: printsRef.current,
              }));
            }
          }
        } catch {
          // ignore parse errors
        }
      };

      ws.onclose = () => {
        if (!mountedRef.current || ws !== wsRef.current) return;
        connectedRef.current = false;
        if (uiActiveRef.current) {
          setState(s => ({ ...s, connected: false, prints: printsRef.current }));
        }
        const delay = backoffRef.current;
        backoffRef.current = Math.min(delay * 2, 30_000);
        reconnectTimerRef.current = setTimeout(connect, delay);
      };
    }

    connect();

    return () => {
      mountedRef.current = false;
      raf.cancel();
      if (reconnectTimerRef.current != null) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      const ws = wsRef.current;
      wsRef.current = null;
      ws?.close();
    };
  }, [symbol]);

  return state;
}
