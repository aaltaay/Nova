import { useEffect, useRef, useState } from 'react';
import { WS_BASE_URL } from '../constants';
import { shouldKeepPriorBook } from './depthBookGuards';
import type { DepthBook } from './types';

interface DepthState {
  book: DepthBook | null;
  connected: boolean;
  l1Fallback: boolean;
  error: string | null;
}

/**
 * Opens /ws/ibkr/depth/{symbol}, receives book updates.
 * Reconnects on disconnect. Keeps the last book visible across brief
 * reconnects so the ladder does not flash "Connecting depth…" every cycle.
 *
 * Symbol gate: ignore books / events from a stale WebSocket or whose
 * ``msg.symbol`` does not match the hook's current symbol. Without this,
 * a late NXTC book can paint under an MVO quote after a fast switch.
 */
export function useIbkrDepth(symbol: string | null): DepthState {
  const [state, setState] = useState<DepthState>({
    book: null,
    connected: false,
    l1Fallback: false,
    error: null,
  });
  const wsRef = useRef<WebSocket | null>(null);
  const backoffRef = useRef(1000);
  const mountedRef = useRef(true);
  // Tracks the pending setTimeout(connect, delay) from ws.onclose so the
  // cleanup below can cancel it. Without this, switching symbols right after
  // a stale connection closes lets that reconnect fire late: mountedRef is
  // back to true (set by the new effect run) but the closure still targets
  // the OLD symbol, so it opens a second WebSocket that overwrites wsRef —
  // orphaning the real (new-symbol) connection with no way to close it. The
  // orphan never sends a close frame, so the backend's per-symbol viewer
  // count for the old symbol never reaches zero and that depth slot leaks
  // for the rest of the session (see PROBLEM_LOG "IBKR_MAX_DEPTH_SYMBOLS
  // slots leak, Level 2 keeps reconnecting for every symbol after ~3
  // switches").
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    const symKey = symbol ? symbol.toUpperCase() : null;

    if (!symKey) {
      setState({ book: null, connected: false, l1Fallback: false, error: null });
      return;
    }

    // Symbol changed — drop the previous book so we never paint SHPH under EHGO.
    setState({ book: null, connected: false, l1Fallback: false, error: null });

    function connect() {
      if (!mountedRef.current) return;
      const ws = new WebSocket(`${WS_BASE_URL}/ws/ibkr/depth/${symKey}`);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current || ws !== wsRef.current) return;
        backoffRef.current = 1000;
      };

      ws.onmessage = (e) => {
        if (!mountedRef.current || ws !== wsRef.current) return;
        try {
          const msg = JSON.parse(e.data as string);
          const msgSym = typeof msg.symbol === 'string' ? msg.symbol.toUpperCase() : null;
          if (msgSym != null && msgSym !== symKey) return;

          if (msg.type === 'subscribed') {
            setState(s => ({ ...s, connected: true, error: null }));
          } else if (msg.type === 'book') {
            const book: DepthBook = { ...msg.data, symbol: symKey };
            setState(s => {
              if (shouldKeepPriorBook(book, s.book)) {
                return { ...s, connected: true, error: null };
              }
              return {
                book,
                connected: true,
                l1Fallback: book.l1_fallback,
                error: null,
              };
            });
          } else if (msg.type === 'error') {
            setState(s => ({
              ...s,
              connected: false,
              error: typeof msg.message === 'string' ? msg.message : 'Depth error',
            }));
          }
        } catch {
          // ignore parse errors
        }
      };

      // Do not flip connected=false on onerror alone — browsers often fire
      // onerror immediately before onclose, and that alone was enough to swap
      // a healthy ladder for "Connecting depth…" for a frame.
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
