import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { WS_BASE_URL } from '../constants';
import { SAMPLE_LIVE_FEED_ABSENT } from '../sample_data/sampleCopy';
import { onSampleDesk } from '../sample_data/sampleOrderGuard';
import { shouldKeepPriorBook } from './depthBookGuards';
import type { DepthBook } from './types';

interface DepthState {
  book: DepthBook | null;
  connected: boolean;
  l1Fallback: boolean;
  error: string | null;
}

const EMPTY: DepthState = {
  book: null,
  connected: false,
  l1Fallback: false,
  error: null,
};

/**
 * Opens /ws/ibkr/depth/{symbol}, receives book updates.
 * Reconnects on disconnect. Keeps the last book visible across brief
 * reconnects so the ladder does not flash "Connecting depth…" every cycle.
 *
 * Symbol gate: ignore books / events from a stale WebSocket or whose
 * ``msg.symbol`` does not match the hook's current symbol. Without this,
 * a late NXTC book can paint under an MVO quote after a fast switch.
 *
 * Hidden live tabs keep the socket and latest book in refs. React / ladder
 * paint waits until ``uiActive`` so a background tab cannot burn the main thread.
 */
export function useIbkrDepth(symbol: string | null, uiActive = true): DepthState {
  const [state, setState] = useState<DepthState>(EMPTY);
  const wsRef = useRef<WebSocket | null>(null);
  const backoffRef = useRef(1000);
  const mountedRef = useRef(true);
  // Tracks the pending setTimeout(connect, delay) from ws.onclose so the
  // cleanup below can cancel it. Without this, switching symbols right after
  // a stale connection closes lets that reconnect fire late: mountedRef is
  // back to true (set by the new effect run) but the closure still targets
  // the OLD symbol, so it opens a second WebSocket that overwrites wsRef --
  // orphaning the real (new-symbol) connection with no way to close it. The
  // orphan never sends a close frame, so the backend's per-symbol viewer
  // count for the old symbol never reaches zero and that depth slot leaks
  // for the rest of the session (see PROBLEM_LOG "IBKR_MAX_DEPTH_SYMBOLS
  // slots leak, Level 2 keeps reconnecting for every symbol after ~3
  // switches").
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const uiActiveRef = useRef(uiActive);
  const bookRef = useRef<DepthBook | null>(null);
  const connectedRef = useRef(false);
  const l1FallbackRef = useRef(false);
  const errorRef = useRef<string | null>(null);

  useEffect(() => {
    uiActiveRef.current = uiActive;
  }, [uiActive]);

  const commitUi = () => {
    if (!mountedRef.current) return;
    setState({
      book: bookRef.current,
      connected: connectedRef.current,
      l1Fallback: l1FallbackRef.current,
      error: errorRef.current,
    });
  };

  useLayoutEffect(() => {
    if (!uiActive) return;
    commitUi();
  }, [uiActive]);

  useEffect(() => {
    mountedRef.current = true;
    const symKey = symbol ? symbol.toUpperCase() : null;

    bookRef.current = null;
    connectedRef.current = false;
    l1FallbackRef.current = false;
    errorRef.current = null;
    setState(EMPTY);

    if (!symKey) {
      return;
    }

    // V4: the sample desk takes no live IBKR depth line -- a stated absence instead.
    if (onSampleDesk()) {
      errorRef.current = SAMPLE_LIVE_FEED_ABSENT;
      setState({ ...EMPTY, error: SAMPLE_LIVE_FEED_ABSENT });
      return;
    }

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
            connectedRef.current = true;
            errorRef.current = null;
            if (uiActiveRef.current) commitUi();
          } else if (msg.type === 'book') {
            const book: DepthBook = { ...msg.data, symbol: symKey };
            if (shouldKeepPriorBook(book, bookRef.current)) {
              connectedRef.current = true;
              errorRef.current = null;
            } else {
              bookRef.current = book;
              connectedRef.current = true;
              l1FallbackRef.current = book.l1_fallback;
              errorRef.current = null;
            }
            if (uiActiveRef.current) commitUi();
          } else if (msg.type === 'error') {
            connectedRef.current = false;
            errorRef.current = typeof msg.message === 'string' ? msg.message : 'Depth error';
            if (uiActiveRef.current) commitUi();
          }
        } catch {
          // ignore parse errors
        }
      };

      // Do not flip connected=false on onerror alone -- browsers often fire
      // onerror immediately before onclose, and that alone was enough to swap
      // a healthy ladder for "Connecting depth…" for a frame.
      ws.onclose = () => {
        if (!mountedRef.current || ws !== wsRef.current) return;
        connectedRef.current = false;
        if (uiActiveRef.current) commitUi();
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
