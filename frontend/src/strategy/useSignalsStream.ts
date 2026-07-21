/** Opens /ws/strategy, receives recent signal history, then appends live setup signals. */
import { useEffect, useRef, useState } from 'react';
import { WS_BASE_URL } from '../constants';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import type { SetupSignal } from './types';

interface SignalsStreamState {
  signals: SetupSignal[];
  connected: boolean;
}

export function useSignalsStream(): SignalsStreamState {
  const sample = useSampleDataOptional();
  const [signals, setSignals] = useState<SetupSignal[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const backoffRef = useRef(1000);
  const mountedRef = useRef(true);

  useEffect(() => {
    if (sample) return;
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
          } else if (msg.type === 'signal' || msg.type === 'decision') {
            const { type: _type, decision: _d, reason_codes: _r, mode: _m, would_execute: _w, receipt_id: _rid, ...rest } = msg;
            const signal = rest as SetupSignal;
            // P2+ decision frames carry nova_os on the signal dict; top-level fields are also present.
            if (msg.type === 'decision' && !signal.nova_os && msg.decision) {
              (signal as SetupSignal & { nova_os?: object }).nova_os = {
                decision: msg.decision,
                reason_codes: msg.reason_codes,
                mode: msg.mode,
                would_execute: msg.would_execute,
                receipt_id: msg.receipt_id,
              };
            }
            setSignals(prev => [signal, ...prev]);
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
  }, [sample]);

  if (sample) {
    return { signals: sample.signals, connected: true };
  }

  return { signals, connected };
}
