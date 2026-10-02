import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { WS_BASE_URL } from '../constants';
import { L2_LENT_POLL_MS } from '../constantGroups/market_ui';
import { SAMPLE_LIVE_FEED_ABSENT } from '../sample_data/sampleCopy';
import { onSampleDesk } from '../sample_data/sampleOrderGuard';
import { shouldKeepPriorBook } from './depthBookGuards';
import { applyBookWatchFrame, type BookWatchState } from './bookWatch';
import { pollLoan, type DepthLoan } from './depthLines';
import type { DepthLentTo } from './depthUiStatus';
import type { DepthBook } from './types';
import { countSocketMessage, frameBytes } from '../perf/perfCounters';

/** The line went to a setup (ADR 043): the tab shows why and waits for it to come back. */
export interface DepthLent extends DepthLentTo {
  since: number | null;
  /** The backend's sentence (the ladder builds its own from the fields above). */
  text: string | null;
}

interface DepthState {
  book: DepthBook | null;
  connected: boolean;
  l1Fallback: boolean;
  error: string | null;
  /** The book watcher's verdicts on this live line (ADR 033 amendment); null until its first frame. */
  watch: BookWatchState | null;
  /** The line is lent to one of Nova's setups (ADR 043 decision 6); null while this tab has it. */
  lent: DepthLent | null;
}

export interface DepthOptions {
  /**
   * A Trader tab's Level 2: its socket says so (`tab=1`), so the backend may lend the line while no
   * visible window shows the tab. Any Level 2 says whether it is in front (`front=1`), which recalls
   * a loan of its line.
   */
  traderTab?: boolean;
}

const EMPTY: DepthState = {
  book: null,
  connected: false,
  l1Fallback: false,
  error: null,
  watch: null,
  lent: null,
};

function str(v: unknown): string | null {
  return typeof v === 'string' && v ? v : null;
}

function lentFromFrame(msg: Record<string, unknown>): DepthLent {
  const to = (msg.to ?? {}) as Record<string, unknown>;
  return {
    symbol: str(to.symbol)?.toUpperCase() ?? null,
    setupType: str(to.setup_type),
    tier: str(msg.tier),
    why: str(msg.why),
    since: typeof msg.since === 'number' ? msg.since : null,
    text: str(msg.text),
  };
}

/** The poll's word on a standing loan: its reason moves (armed, then near, then a trade). */
function lentFromLoan(loan: DepthLoan): DepthLent {
  return {
    symbol: loan.borrower, setupType: loan.setup_type, tier: loan.tier, why: loan.why, since: loan.since,
    text: loan.text,
  };
}

function documentVisible(): boolean {
  return typeof document === 'undefined' || document.visibilityState !== 'hidden';
}

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
 *
 * A lent line (ADR 043 decision 6): the backend sends `{type: "lent", ...}` and closes. The hook
 * then never reconnects by its backoff: it asks `GET /api/ibkr/depth/lines` every L2_LENT_POLL_MS
 * and reconnects once no loan names this symbol -- or at once when this Level 2 comes to the front
 * (`uiActive` and the document visible), which opens with `front=1` and recalls the loan.
 */
export function useIbkrDepth(symbol: string | null, uiActive = true, options: DepthOptions = {}): DepthState {
  const traderTab = options.traderTab === true;
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
  const watchRef = useRef<BookWatchState | null>(null);
  const lentRef = useRef<DepthLent | null>(null);
  // Set by the socket effect: take a lent line back now if this Level 2 is in front.
  const wakeRef = useRef<() => void>(() => {});

  useEffect(() => {
    uiActiveRef.current = uiActive;
    if (uiActive) wakeRef.current();
  }, [uiActive]);

  const commitUi = () => {
    if (!mountedRef.current) return;
    setState({
      book: bookRef.current,
      connected: connectedRef.current,
      l1Fallback: l1FallbackRef.current,
      error: errorRef.current,
      watch: watchRef.current,
      lent: lentRef.current,
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
    watchRef.current = null;
    lentRef.current = null;
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

    const inFront = () => uiActiveRef.current && documentVisible();
    let pollTimer: ReturnType<typeof setInterval> | null = null;
    let pollAbort: AbortController | null = null;
    // The socket asking for the line back is open; the lent words stay until it answers.
    let takingBack = false;

    function stopPoll() {
      if (pollTimer != null) {
        clearInterval(pollTimer);
        pollTimer = null;
      }
      pollAbort?.abort();
      pollAbort = null;
    }

    /** The loan ended, or this Level 2 came to the front (its socket recalls the loan): ask for the line now. */
    function takeBack() {
      if (!lentRef.current || takingBack) return;
      takingBack = true;
      stopPoll();
      backoffRef.current = 1000;
      connect();
    }

    /** The socket that asked answered: the line is this tab's again (or it says why not). */
    function settle() {
      takingBack = false;
      lentRef.current = null;
    }

    async function pollOnce() {
      if (pollAbort || takingBack || !mountedRef.current || !lentRef.current || !symKey) return;
      const ctrl = new AbortController();
      pollAbort = ctrl;
      const got = await pollLoan(symKey, ctrl.signal);
      if (pollAbort === ctrl) pollAbort = null;
      if (ctrl.signal.aborted || !mountedRef.current || !lentRef.current) return;
      if (got.kind === 'ended') {
        takeBack();
      } else if (got.kind === 'standing') {
        lentRef.current = lentFromLoan(got.loan);
        if (uiActiveRef.current) commitUi();
      }
      // 'unknown': the backend did not answer -- still lent; the next poll asks again.
    }

    function startPoll() {
      if (pollTimer == null) pollTimer = setInterval(() => void pollOnce(), L2_LENT_POLL_MS);
    }

    wakeRef.current = () => {
      if (lentRef.current && inFront()) takeBack();
    };
    const onVisibility = () => wakeRef.current();
    if (typeof document !== 'undefined') document.addEventListener('visibilitychange', onVisibility);

    function connect() {
      if (!mountedRef.current) return;
      const params = `?${traderTab ? 'tab=1&' : ''}front=${inFront() ? 1 : 0}`;
      const ws = new WebSocket(`${WS_BASE_URL}/ws/ibkr/depth/${symKey}${params}`);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current || ws !== wsRef.current) return;
        backoffRef.current = 1000;
      };

      ws.onmessage = (e) => {
        countSocketMessage('depth', frameBytes(e.data));
        if (!mountedRef.current || ws !== wsRef.current) return;
        try {
          const msg = JSON.parse(e.data as string);
          const msgSym = typeof msg.symbol === 'string' ? msg.symbol.toUpperCase() : null;
          if (msgSym != null && msgSym !== symKey) return;
          if (lentRef.current && (msg.type === 'subscribed' || msg.type === 'book' || msg.type === 'error')) {
            settle();
          }

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
          } else if (msg.type === 'book_watch') {
            // What left the book: a reset frame on every (re)connect, then each verdict once.
            watchRef.current = applyBookWatchFrame(watchRef.current, msg.data, Date.now());
            if (uiActiveRef.current) commitUi();
          } else if (msg.type === 'lent') {
            // Lent to a setup (ADR 043): this book is no longer live; the socket closes next.
            takingBack = false;
            lentRef.current = lentFromFrame(msg);
            bookRef.current = null;
            watchRef.current = null;
            connectedRef.current = false;
            errorRef.current = null;
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
        if (lentRef.current && takingBack) {
          settle();                          // it closed before answering: the backoff takes over from here
        } else if (lentRef.current) {
          // Never by the backoff: when the loan ends (the poll), or now if this Level 2 is in front.
          if (uiActiveRef.current) commitUi();
          if (inFront()) takeBack();
          else startPoll();
          return;
        }
        if (uiActiveRef.current) commitUi();
        const delay = backoffRef.current;
        backoffRef.current = Math.min(delay * 2, 30_000);
        reconnectTimerRef.current = setTimeout(connect, delay);
      };
    }

    connect();

    return () => {
      mountedRef.current = false;
      wakeRef.current = () => {};
      if (typeof document !== 'undefined') document.removeEventListener('visibilitychange', onVisibility);
      stopPoll();
      if (reconnectTimerRef.current != null) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      const ws = wsRef.current;
      wsRef.current = null;
      ws?.close();
    };
  }, [symbol, traderTab]);

  return state;
}
