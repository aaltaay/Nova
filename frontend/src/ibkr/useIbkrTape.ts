import { useEffect, useRef, useState } from 'react';
import { WS_BASE_URL } from '../constants';
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
 * Symbol gate: msg.symbol must match the hook's current symbol — same
 * class of guard as useIbkrDepth to prevent cross-symbol bleed.
 */
export function useIbkrTape(symbol: string | null): TapeState {
  const [state, setState] = useState<TapeState>(emptyTapeState);
  const wsRef = useRef<WebSocket | null>(null);
  const backoffRef = useRef(1000);
  const mountedRef = useRef(true);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    const symKey = tapeSymbolKey(symbol);

    if (!symKey) {
      setState(emptyTapeState());
      return;
    }

    // Clear tape immediately on symbol change — never show previous symbol's prints.
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
            setState(s => ({ ...s, connected: true, error: null }));
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
            setState(s => ({
              ...s,
              prints: appendTapePrint(s.prints, print),
            }));
          } else if (msg.type === 'error') {
            setState(s => ({
              ...s,
              connected: false,
              error: typeof msg.message === 'string' ? msg.message : 'Tape error',
            }));
          }
        } catch {
          // ignore parse errors
        }
      };

      ws.onclose = () => {
        if (!mountedRef.current || ws !== wsRef.current) return;
        setState(s => ({ ...s, connected: false }));
        const delay = backoffRef.current;
        backoffRef.current = Math.min(delay * 2, 30_000);
        reconnectTimerRef.current = setTimeout(connect, delay);
      };
    }

    connect();

    return () => {
      mountedRef.current = false;
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
