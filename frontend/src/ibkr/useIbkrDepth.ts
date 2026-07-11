import { useEffect, useRef, useState } from 'react';
import { WS_BASE_URL } from '../constants';
import type { DepthBook } from './types';

interface DepthState {
  book: DepthBook | null;
  connected: boolean;
  l1Fallback: boolean;
}

/**
 * Opens /ws/ibkr/depth/{symbol}, receives book updates.
 * Reconnects on disconnect. Returns null book when not yet received.
 */
export function useIbkrDepth(symbol: string | null): DepthState {
  const [state, setState] = useState<DepthState>({ book: null, connected: false, l1Fallback: false });
  const wsRef = useRef<WebSocket | null>(null);
  const backoffRef = useRef(1000);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;

    if (!symbol) {
      setState({ book: null, connected: false, l1Fallback: false });
      return;
    }

    function connect() {
      if (!mountedRef.current) return;
      const ws = new WebSocket(`${WS_BASE_URL}/ws/ibkr/depth/${symbol}`);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current) return;
        backoffRef.current = 1000;
      };

      ws.onmessage = (e) => {
        if (!mountedRef.current) return;
        try {
          const msg = JSON.parse(e.data as string);
          if (msg.type === 'subscribed') {
            setState(s => ({ ...s, connected: true }));
          } else if (msg.type === 'book') {
            const book: DepthBook = msg.data;
            setState({ book, connected: true, l1Fallback: book.l1_fallback });
          } else if (msg.type === 'error') {
            setState(s => ({ ...s, connected: false }));
          }
        } catch {
          // ignore parse errors
        }
      };

      ws.onerror = () => {
        if (!mountedRef.current) return;
        setState(s => ({ ...s, connected: false }));
      };

      ws.onclose = () => {
        if (!mountedRef.current) return;
        setState(s => ({ ...s, connected: false }));
        const delay = backoffRef.current;
        backoffRef.current = Math.min(delay * 2, 30_000);
        setTimeout(connect, delay);
      };
    }

    connect();

    return () => {
      mountedRef.current = false;
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [symbol]);

  return state;
}
