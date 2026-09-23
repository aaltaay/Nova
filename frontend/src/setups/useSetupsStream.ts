/** Live Setups board over `/ws/setups` (ADR 022). The sample desk never opens
 * the socket; it reads the Nova Marketing Sample Data board instead. */
import { useEffect, useRef, useState } from 'react';
import { SETUPS_RECONNECT_MAX_MS, SETUPS_WS_PATH, WS_BASE_URL } from '../constants';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import { SAMPLE_SETUPS_BOARD } from '../sample_data/sampleSetups';
import { noteSetupProposal } from './setupsSound';
import type { SetupProposal, SetupsBoard } from './types';
import { countSocketMessage, frameBytes } from '../perf/perfCounters';

const GENERATED_AT = /"generated_at":\s*[-0-9.eE+]+/;

export interface SetupsStreamState {
  board: SetupsBoard | null;
  connected: boolean;
}

export function useSetupsStream(enabled = true): SetupsStreamState {
  const sample = useSampleDataOptional();
  const [board, setBoard] = useState<SetupsBoard | null>(null);
  const [connected, setConnected] = useState(false);
  const backoff = useRef(1000);
  const mounted = useRef(true);
  const lastFrame = useRef('');

  useEffect(() => {
    if (sample || !enabled) return;
    mounted.current = true;
    let ws: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout> | null = null;

    function connect() {
      if (!mounted.current) return;
      ws = new WebSocket(`${WS_BASE_URL}${SETUPS_WS_PATH}`);
      ws.onopen = () => {
        if (!mounted.current) return;
        setConnected(true);
        backoff.current = 1000;
      };
      ws.onmessage = (e) => {
        countSocketMessage('setups', frameBytes(e.data));
        if (!mounted.current) return;
        const raw = String(e.data);
        // A board frame is pushed every second; one that differs only in its
        // stamp would re-render every reader for nothing.
        const same = raw.replace(GENERATED_AT, '');
        if (same === lastFrame.current) return;
        let msg: { type?: string; alerts?: SetupProposal[] } & Partial<SetupsBoard>;
        try {
          msg = JSON.parse(raw);
        } catch {
          return;
        }
        if (msg.type === 'board') lastFrame.current = same;
        if (msg.type === 'board' && Array.isArray(msg.rows)) {
          setBoard(msg as SetupsBoard);
        } else if (msg.type === 'alerts' && Array.isArray(msg.alerts)) {
          for (const a of msg.alerts) noteSetupProposal(a.id);
        }
      };
      ws.onclose = () => {
        if (!mounted.current) return;
        setConnected(false);
        lastFrame.current = '';
        const delay = backoff.current;
        backoff.current = Math.min(delay * 2, SETUPS_RECONNECT_MAX_MS);
        retry = setTimeout(connect, delay);
      };
      ws.onerror = () => {
        if (mounted.current) setConnected(false);
      };
    }

    connect();
    return () => {
      mounted.current = false;
      if (retry) clearTimeout(retry);
      ws?.close();
    };
  }, [sample, enabled]);

  if (sample) return { board: SAMPLE_SETUPS_BOARD, connected: true };
  return { board, connected };
}
