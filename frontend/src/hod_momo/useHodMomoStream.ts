import { useEffect, useRef, useState } from 'react';
import { WS_BASE_URL } from '../constants';
import type { AlertObject } from './types';

interface HodMomoStreamState {
  alerts: AlertObject[];
  connected: boolean;
}

/**
 * Opens /ws/hod-momo, receives the initial alert list, then appends live alerts.
 * Automatically reconnects on disconnect with exponential backoff.
 * New alerts are prepended so the list stays newest-first.
 */
export function useHodMomoStream(): HodMomoStreamState {
  const [alerts, setAlerts] = useState<AlertObject[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const backoffRef = useRef(1000);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;

    function connect() {
      if (!mountedRef.current) return;
      const ws = new WebSocket(`${WS_BASE_URL}/ws/hod-momo`);
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
            setAlerts(Array.isArray(msg.alerts) ? msg.alerts : []);
          } else if (msg.type === 'alert') {
            setAlerts(prev => [msg.alert as AlertObject, ...prev]);
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

  return { alerts, connected };
}
