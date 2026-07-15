import { useEffect, useRef, useState } from 'react';
import { HOD_MOMO_ALERT_BATCH_MS, WS_BASE_URL } from '../constants';
import type { AlertObject } from './types';

interface HodMomoStreamState {
  /** Newest-first full day list — table virtualizes; nothing is discarded. */
  alerts: AlertObject[];
  /** Same as alerts.length (kept for badge / header). */
  totalToday: number;
  connected: boolean;
}

/**
 * Opens /ws/hod-momo, receives today's full alert list, then batches live alerts.
 * Keeps every alert in memory; the table only mounts the visible row window.
 * Batching limits App re-render rate without dropping older entries.
 */
export function useHodMomoStream(): HodMomoStreamState {
  const [alerts, setAlerts] = useState<AlertObject[]>([]);
  const [totalToday, setTotalToday] = useState(0);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const backoffRef = useRef(1000);
  const mountedRef = useRef(true);
  const pendingRef = useRef<AlertObject[]>([]);
  const flushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    mountedRef.current = true;

    function flushPending() {
      flushTimerRef.current = null;
      if (!mountedRef.current || pendingRef.current.length === 0) return;
      const batch = pendingRef.current;
      pendingRef.current = [];
      setAlerts(prev => {
        const next = [...batch, ...prev];
        setTotalToday(next.length);
        return next;
      });
    }

    function scheduleFlush() {
      if (flushTimerRef.current != null) return;
      flushTimerRef.current = setTimeout(flushPending, HOD_MOMO_ALERT_BATCH_MS);
    }

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
            pendingRef.current = [];
            if (flushTimerRef.current != null) {
              clearTimeout(flushTimerRef.current);
              flushTimerRef.current = null;
            }
            const list = Array.isArray(msg.alerts) ? (msg.alerts as AlertObject[]) : [];
            setAlerts(list);
            setTotalToday(
              typeof msg.total === 'number' && msg.total >= 0 ? msg.total : list.length,
            );
          } else if (msg.type === 'alert' && msg.alert) {
            pendingRef.current.push(msg.alert as AlertObject);
            scheduleFlush();
          }
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
      if (flushTimerRef.current != null) clearTimeout(flushTimerRef.current);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, []);

  return { alerts, totalToday, connected };
}
