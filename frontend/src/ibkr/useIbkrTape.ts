import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { WS_BASE_URL } from '../constants';
import { upsertTapePrint10SecBar } from '../chart/barsStore';
import { forgetBackendGate, noteBackendGate, noteLinkQuiet } from '../market_view';
import { noteHeatPrint, resetHeat } from '../heat_map';
import { SAMPLE_LIVE_FEED_ABSENT } from '../sample_data/sampleCopy';
import { onSampleDesk } from '../sample_data/sampleOrderGuard';
import { createRafCoalesce } from '../utils/rafCoalesce';
import { LANE_PANE_TAPE } from '../constantGroups/market_ui';
import { LINK_PANE_TAPE } from '../constantGroups/market_view';
import { documentVisible, LaneWait } from './laneWait';
import { SocketWatch } from './socketWatch';
import {
  appendTapePrint,
  applyTapeSilentRecoveryFrame,
  emptyTapeState,
  parseTapeSilence,
  tapeMessageAllowed,
  tapePrintFromWire,
  tapeSymbolKey,
  wireSeq,
  type TapePrint,
  type TapeSilence,
  type TapeState,
  type TapeWirePrint,
} from './tapeFeed';
import { countSocketMessage, frameBytes } from '../perf/perfCounters';

export type { TapePrint, TapeState, TapeSide } from './tapeFeed';

export interface TapeOptions {
  /**
   * A Trader tab's Time & Sales: its socket says so (`tab=1`), so the backend knows a hidden tab from a pane
   * shown elsewhere. Any Time & Sales says whether it is in front (`front=1`), which moves your lane to its
   * stock (ADR 071).
   */
  traderTab?: boolean;
  /**
   * Ask the PC for the prints it already holds for the line (`?recent=<n>`, and after a drop `&after=<seq>`:
   * `architecture/schema/execution.md`), so the tape does not open empty and a reconnect leaves no hole. The phone.
   */
  recent?: number;
  /**
   * Watch the socket itself (`socketWatch.ts`): one that goes quiet is said (`quietSince`), holds new buys on the
   * stock, and is dropped and asked for again at once. For a page that is not on the PC (the phone); the desk's
   * own socket is local, and a reconnect there would drop a backlog (ADR 045).
   */
  watchLink?: boolean;
}

/**
 * Opens /ws/ibkr/tape/{symbol}, receives AllLast tick-by-tick prints.
 * Reconnects on disconnect. Clears prints on symbol change.
 *
 * Symbol gate: msg.symbol must match the hook's current symbol -- same
 * class of guard as useIbkrDepth to prevent cross-symbol bleed.
 *
 * Prints always land on the ordered ring. React state flushes once per
 * animation frame while ``uiActive``. Hidden live tabs keep the socket and
 * ring (and 10Sec upsert); they do not commit tape UI until shown again.
 *
 * No lane on the stock (ADR 071): the backend sends `{type: "lane", ...}` and closes. The ring is
 * cleared (the tape is no longer live, and a gap would not show), the pane says where your lane is, and
 * the hook never reconnects by its backoff (LaneWait): it asks again when the operator brings it to the
 * front or clicks its words (your lane comes here), or when the lanes poll finds a lane on its stock --
 * the same moments as the tab's Level 2.
 *
 * A live line with no print for a while (#722): each idle `ping` carries the backend's reading
 * (`silence`: halted, silent or quiet), and any print clears it. Each ping, and a `gate` frame whenever it
 * changes, also carries the order gate's answer for the symbol (ADR 045 amendment 2026-10-14): the market view
 * registry locks the ticket with the door's own words while Time & Sales misses trades.
 *
 * A print whose `seq` the ring already has is never added twice, so the prints the PC holds (`recent`) can be
 * asked for again after any drop. Those go to the rows only: the 10-second candle and the heat map take live prints.
 */
export function useIbkrTape(symbol: string | null, uiActive = true, options: TapeOptions = {}): TapeState {
  const traderTab = options.traderTab === true;
  const recent = Math.max(0, Math.floor(options.recent ?? 0));
  const watchLink = options.watchLink === true;
  const [state, setState] = useState<TapeState>(emptyTapeState);
  const wsRef = useRef<WebSocket | null>(null);
  const backoffRef = useRef(1000);
  const mountedRef = useRef(true);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const printsRef = useRef<TapePrint[]>([]);
  const uiActiveRef = useRef(uiActive);
  const connectedRef = useRef(false);
  const errorRef = useRef<string | null>(null);
  // When the backend asks IBKR again for a refused line (#698); null when it is not retrying.
  const retryAtRef = useRef<number | null>(null);
  // This symbol's wait for a lane; set by the socket effect.
  const lineRef = useRef<LaneWait | null>(null);
  // The backend's word on a line with no print for a while (#722); null while it prints.
  const silenceRef = useRef<TapeSilence | null>(null);
  // The newest `seq` on the ring: what the PC is asked to send from after a drop, and what a repeat is known by.
  const lastSeqRef = useRef<number | null>(null);
  // Since when this socket has said nothing (watchLink); null while it speaks.
  const quietSinceRef = useRef<number | null>(null);
  const watchLinkRef = useRef(watchLink);
  watchLinkRef.current = watchLink;

  useEffect(() => {
    uiActiveRef.current = uiActive;
    if (uiActive) lineRef.current?.wake();     // shown: your lane comes here
  }, [uiActive]);


  const commitUi = () => {
    if (!mountedRef.current) return;
    setState({
      prints: printsRef.current,
      connected: connectedRef.current,
      error: errorRef.current,
      laneWait: lineRef.current?.waiting ?? null,
      retryAt: retryAtRef.current,
      silence: silenceRef.current,
      ...(watchLinkRef.current ? { quietSince: quietSinceRef.current } : {}),
    });
  };

  const rafRef = useRef(createRafCoalesce(commitUi));

  useLayoutEffect(() => {
    if (!uiActive) return;
    rafRef.current.flushNow();
  }, [uiActive]);

  useEffect(() => {
    mountedRef.current = true;
    const symKey = tapeSymbolKey(symbol);
    const raf = rafRef.current;

    printsRef.current = [];
    connectedRef.current = false;
    errorRef.current = null;
    retryAtRef.current = null;
    lineRef.current = null;
    silenceRef.current = null;
    lastSeqRef.current = null;
    quietSinceRef.current = null;
    raf.cancel();
    setState(emptyTapeState());

    if (!symKey) {
      return;
    }

    // V4: the sample desk opens no live tape line -- a stated absence instead.
    if (onSampleDesk()) {
      errorRef.current = SAMPLE_LIVE_FEED_ABSENT;
      setState({ ...emptyTapeState(), error: SAMPLE_LIVE_FEED_ABSENT });
      return;
    }

    const inFront = () => uiActiveRef.current && documentVisible();
    const line = new LaneWait(symKey, LANE_PANE_TAPE, {
      inFront,
      // A lane came to this stock, or the operator brought this Time & Sales here: ask now.
      reconnect: (front) => {
        backoffRef.current = 1000;
        connect(front);
      },
      changed: () => {
        if (uiActiveRef.current) commitUi();
      },
    });
    lineRef.current = line;

    // The `front` the socket now open was asked with: a socket replaced for being quiet asks with the same one,
    // so a reconnect never moves your lane by itself (ADR 071).
    let frontNow = false;
    const speaks = () => {
      if (quietSinceRef.current == null) return;
      quietSinceRef.current = null;
      noteLinkQuiet(symKey, LINK_PANE_TAPE, null);
      if (uiActiveRef.current) commitUi();
    };
    const watch = watchLink
      ? new SocketWatch({
          // Nothing from the PC on this socket: say so, hold new buys on the stock, and ask again now.
          quiet: (since) => {
            quietSinceRef.current = quietSinceRef.current ?? since;
            connectedRef.current = false;
            noteLinkQuiet(symKey, LINK_PANE_TAPE, quietSinceRef.current);
            forgetBackendGate(symKey);
            if (uiActiveRef.current) commitUi();
            const old = wsRef.current;
            wsRef.current = null;      // its close is no longer this hook's
            old?.close();
            connect(frontNow);
          },
          // Back in front, or back online: a reconnect waiting on its backoff is made now.
          woke: () => {
            if (reconnectTimerRef.current == null) return;
            clearTimeout(reconnectTimerRef.current);
            reconnectTimerRef.current = null;
            backoffRef.current = 1000;
            connect();
          },
        })
      : null;

    function connect(front = inFront()) {
      if (!mountedRef.current) return;
      frontNow = front;
      const held = recent > 0 ? `&recent=${recent}${lastSeqRef.current != null ? `&after=${lastSeqRef.current}` : ''}` : '';
      const params = `?${traderTab ? 'tab=1&' : ''}front=${front ? 1 : 0}${held}`;
      const ws = new WebSocket(`${WS_BASE_URL}/ws/ibkr/tape/${symKey}${params}`);
      wsRef.current = ws;
      watch?.opened();

      ws.onopen = () => {
        if (!mountedRef.current || ws !== wsRef.current) return;
        backoffRef.current = 1000;
      };

      ws.onmessage = (e) => {
        countSocketMessage('tape', frameBytes(e.data));
        if (!mountedRef.current || ws !== wsRef.current) return;
        watch?.heard();
        speaks();
        try {
          const msg = JSON.parse(e.data as string);
          if (!tapeMessageAllowed(msg.symbol, symKey!)) return;
          if (msg.type === 'subscribed' || msg.type === 'print' || msg.type === 'prints' || msg.type === 'error') {
            line.answered();
          }

          // The order gate's own answer for this stock (ADR 045 amendment 2026-10-14): the ticket locks with it.
          if (msg.type === 'gate') {
            noteBackendGate(symKey!, msg.gate ?? null);
            return;
          }

          const silentRecovery =
            msg.type === 'error' ? applyTapeSilentRecoveryFrame(silenceRef.current, msg) : null;
          if (msg.type !== 'ping' && silentRecovery == null) {
            silenceRef.current = null;  // a print, or any non-silence word on the line, ends a silence
          }

          if (msg.type === 'ping') {
            noteBackendGate(symKey!, msg.gate);
            const next = parseTapeSilence(msg.silence);
            const prev = silenceRef.current;
            if (next != null && (!connectedRef.current && errorRef.current == null)) {
              connectedRef.current = true;
            }
            if (
              next?.state !== prev?.state ||
              next?.since !== prev?.since ||
              next?.text !== prev?.text ||
              next?.recovery?.state !== prev?.recovery?.state ||
              next?.recovery?.text !== prev?.recovery?.text
            ) {
              silenceRef.current = next;
              if (uiActiveRef.current) commitUi();
            }
            return;
          }

          if (msg.type === 'scrub_reset') {
            printsRef.current = [];
            resetHeat(symKey!);
            connectedRef.current = true;
            errorRef.current = null;
            if (uiActiveRef.current) commitUi();
            return;
          }

          if (msg.type === 'subscribed') {
            connectedRef.current = true;
            errorRef.current = null;
            retryAtRef.current = null;
            if (uiActiveRef.current) commitUi();
          } else if (msg.type === 'print' || msg.type === 'prints') {
            // A print means the line works: an error from before it is stale (#698).
            if (errorRef.current != null || !connectedRef.current) {
              connectedRef.current = true;
              errorRef.current = null;
              retryAtRef.current = null;
            }
            // ADR 045: prints waiting together arrive as one `prints` frame, oldest first.
            const items: TapeWirePrint[] = msg.type === 'prints' ? (Array.isArray(msg.items) ? msg.items : []) : [msg];
            // What the PC already held for the line (`recent`): for the rows only.
            const held = msg.type === 'prints' && msg.recent === true;
            for (const item of items) {
              const seq = wireSeq(item);
              if (seq != null) {
                if (lastSeqRef.current != null && seq <= lastSeqRef.current) continue;   // the ring has it
                lastSeqRef.current = seq;
              }
              const print: TapePrint = tapePrintFromWire(item, msg.symbol);
              printsRef.current = appendTapePrint(printsRef.current, print);
              if (held) continue;
              upsertTapePrint10SecBar(symKey!, {
                time: print.time,
                price: print.price,
                size: print.size,
                setsPrice: print.setsPrice,
                // IBKR's own second: the 10-second candle's key, as in IBKR's history (#721).
                exchangeTs: print.exchangeTs,
              });
              // The heat map's dots and volume (ADR 061): the print's own time, size and the desk's side verdict.
              noteHeatPrint(symKey!, print.time, print.price, print.size, print.side);
            }
            if (uiActiveRef.current) raf.schedule();
          } else if (msg.type === 'lane') {
            // No lane is on this stock (ADR 071): this tape is no longer live; the socket closes next.
            line.wait(msg);
            printsRef.current = [];
            connectedRef.current = false;
            errorRef.current = null;
            retryAtRef.current = null;
            raf.cancel();
            if (uiActiveRef.current) commitUi();
          } else if (msg.type === 'error') {
            const retryAt = typeof msg.retry_at === 'number' && Number.isFinite(msg.retry_at) ? msg.retry_at : null;
            if (silentRecovery != null) {
              // Registered-silent recovery (#722): keep existing prints and LINE DOWN badge visible,
              // even on a viewer that receives the broadcast before its own first silence ping.
              if (!connectedRef.current && errorRef.current == null) {
                connectedRef.current = true;
              }
              silenceRef.current = silentRecovery;
              retryAtRef.current = retryAt;
              if (uiActiveRef.current) commitUi();
              return;
            }
            connectedRef.current = false;
            errorRef.current = typeof msg.message === 'string' ? msg.message : 'Tape error';
            retryAtRef.current = retryAt;
            if (uiActiveRef.current) commitUi();
          }
        } catch {
          // ignore parse errors
        }
      };

      ws.onclose = () => {
        if (!mountedRef.current || ws !== wsRef.current) return;
        watch?.closed();
        connectedRef.current = false;
        silenceRef.current = null;
        forgetBackendGate(symKey!);
        // Waiting for a lane: never by the backoff -- the operator brings it, or a lane comes to the stock.
        const waiting = line.closed();
        if (uiActiveRef.current) commitUi();
        if (waiting) return;
        const delay = backoffRef.current;
        backoffRef.current = Math.min(delay * 2, 30_000);
        reconnectTimerRef.current = setTimeout(() => connect(), delay);
      };
    }

    connect();

    return () => {
      mountedRef.current = false;
      raf.cancel();
      watch?.dispose();
      if (quietSinceRef.current != null) noteLinkQuiet(symKey, LINK_PANE_TAPE, null);
      line.dispose();
      if (lineRef.current === line) lineRef.current = null;
      if (reconnectTimerRef.current != null) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      const ws = wsRef.current;
      wsRef.current = null;
      ws?.close();
      forgetBackendGate(symKey);
    };
  }, [symbol, traderTab, recent, watchLink]);

  return state;
}
