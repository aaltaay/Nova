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
  // Ids already applied to state — O(1) membership check so a duplicate
  // broadcast (stale/overlapping WS instance, backend re-send, etc.) can
  // never be pushed into `alerts` twice. Rebuilt only on a fresh `initial`
  // payload, never rescanned from the full day list on every live alert.
  const seenIdsRef = useRef<Set<string>>(new Set());

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

      // Every handler below double-guards on `wsRef.current === ws` (not just
      // `mountedRef`). React StrictMode's dev-mode mount→cleanup→remount can
      // flip `mountedRef` back to true before a just-closed socket's in-flight
      // events finish draining; without the per-instance check, that stale
      // socket kept delivering live 'alert' messages that a newer socket was
      // also receiving — every alert landed in state twice with an identical
      // id, which is what produced the React "duplicate key" storm and the
      // ever-growing, ever-more-expensive alert list.
      ws.onopen = () => {
        if (!mountedRef.current || wsRef.current !== ws) return;
        setConnected(true);
        backoffRef.current = 1000;
      };

      ws.onmessage = (e) => {
        if (!mountedRef.current || wsRef.current !== ws) return;
        try {
          const msg = JSON.parse(e.data as string);
          if (msg.type === 'initial') {
            pendingRef.current = [];
            if (flushTimerRef.current != null) {
              clearTimeout(flushTimerRef.current);
              flushTimerRef.current = null;
            }
            const list = Array.isArray(msg.alerts) ? (msg.alerts as AlertObject[]) : [];
            seenIdsRef.current = new Set(list.map(a => a.id));
            setAlerts(list);
            setTotalToday(
              typeof msg.total === 'number' && msg.total >= 0 ? msg.total : list.length,
            );
          } else if (msg.type === 'alert' && msg.alert) {
            const alert = msg.alert as AlertObject;
            if (seenIdsRef.current.has(alert.id)) return;
            seenIdsRef.current.add(alert.id);
            pendingRef.current.push(alert);
            scheduleFlush();
          }
        } catch {
          // ignore parse errors
        }
      };

      ws.onerror = () => {
        if (!mountedRef.current || wsRef.current !== ws) return;
        setConnected(false);
      };

      ws.onclose = () => {
        if (wsRef.current !== ws) return;
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
      const ws = wsRef.current;
      if (ws) {
        // Detach handlers before closing so a socket that hasn't finished its
        // close handshake yet cannot fire onmessage/onclose into a component
        // instance that's already torn down.
        ws.onopen = null;
        ws.onmessage = null;
        ws.onerror = null;
        ws.onclose = null;
        ws.close();
      }
      wsRef.current = null;
    };
  }, []);

  return { alerts, totalToday, connected };
}
