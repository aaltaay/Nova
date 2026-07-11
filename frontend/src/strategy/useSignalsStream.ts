/** Opens /ws/strategy, receives recent signal history, then appends live setup signals. */
import { useEffect, useRef, useState } from 'react';
import { WS_BASE_URL } from '../constants';
import type { SetupSignal } from './types';

interface SignalsStreamState {
  signals: SetupSignal[];
  connected: boolean;
}

export function useSignalsStream(): SignalsStreamState {
  const [signals, setSignals] = useState<SetupSignal[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const backoffRef = useRef(1000);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;

    function connect() {
      if (!mountedRef.current) return;
      const ws = new WebSocket(`${WS_BASE_URL}/ws/strategy`);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current) return;
        setConnected(true);
        backoffRef.current = 1000;
      };

      ws.onmessage = (e) => {
        if (!mountedRef.current) return;
        try {
          const msg = JSON.parse(e.data as string);
          if (msg.type === 'initial') {
            setSignals(Array.isArray(msg.signals) ? [...msg.signals].reverse() : []);
          } else if (msg.type === 'signal') {
            const { type: _type, ...signal } = msg;
            setSignals(prev => [signal as SetupSignal, ...prev]);
          }
          // ignore "ping"
        } catch {
          // ignore parse errors
        }
      };

      ws.onerror = () => {
        if (!mountedRef.current) return;
        setConnected(false);
      };

      ws.onclose = () => {
        if (!mountedRef.current) return;
        setConnected(false);
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
  }, []);

  return { signals, connected };
}
