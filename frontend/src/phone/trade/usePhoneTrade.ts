/**
 * What the phone's Trade screen trades with: the desk's own Level 2 and Time & Sales sockets for one stock,
 * the desk's read of whether that view is live (market_view), your position and working orders, and the
 * two ways an order leaves -- a one-tap desk action, or the ticket's own order body. Both go out through
 * the desk's ticket code (`runNovaAction`, `placeIbkrOrder`), which the page points at the phone's door.
 *
 * Nothing here judges an order. The gate, the price and the size are the desk's; a refusal is the desk's
 * words, shown as they came.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { findOpenIbkrPosition } from '../../chart/positionOverlay';
import type { NovaActionRecord } from '../../hotkeys/novaActionTypes';
import { runNovaAction, type NovaActionRuntime } from '../../hotkeys/runNovaAction';
import { useIbkrAccountContext } from '../../ibkr/IbkrAccountContext';
import { newGestureKey } from '../../ibkr/gestureKey';
import type { ManualOrderPayload } from '../../ibkr/orderEntry';
import { placeIbkrOrder } from '../../ibkr/placeOrder';
import { depthLentText } from '../../ibkr/lentWords';
import type { DepthBook, IbkrOrder, IbkrPosition } from '../../ibkr/types';
import { useBotsQty } from '../../ibkr/useDeskPositions';
import { useIbkrDepth } from '../../ibkr/useIbkrDepth';
import { useIbkrStatus } from '../../ibkr/useIbkrStatus';
import { useIbkrTape, type TapeState } from '../../ibkr/useIbkrTape';
import { useViewLock, viewStampFor } from '../../market_view';
import { deskNow } from '../../utils/deskClock';
import { usePhoneSession, type TicketAnswer } from '../PhoneSession';

export interface PhoneTrade {
  symbol: string;
  book: DepthBook | null;
  /** Why there is no live Level 2 for the stock, in the desk's words; null while there is one. */
  bookWhy: string | null;
  tape: TapeState;
  bid: number | null;
  ask: number | null;
  /** Your position in the stock; null while flat. */
  position: IbkrPosition | null;
  /** Your shares, signed; 0 while flat. */
  heldQty: number;
  /** The account has been read and is current: a change in `heldQty` from here on is a fill. */
  accountCurrent: boolean;
  /** Every working order on the venue, and the ones on this stock. */
  working: IbkrOrder[];
  workingHere: IbkrOrder[];
  /** Why a new buy is held (the stock's view is behind), in the desk's words; null while it is live. */
  lag: string | null;
  /** The padlock: false while locked. Null before the desk has said. */
  armed: boolean | null;
  /** Run one of the desk's one-tap actions. `how: 'done'` for a cancel. */
  act: (label: string, action: NovaActionRecord, how?: 'sent' | 'done') => void;
  /** Send the ticket's own order. */
  place: (label: string, payload: ManualOrderPayload, referencePrice?: number | null) => void;
}

/** How late the stock's Level 2 reached this phone, ms, as the desk's view registry measured it; null with no book. */
export function level2AgeMs(symbol: string): number | null {
  const desk = viewStampFor(symbol, deskNow()).desk;
  if (!desk) return null;
  const silent = desk.silent_ms ?? 0;
  // A book that arrived on time and then went quiet is as old as the quiet.
  return Math.max(desk.transit_ms ?? 0, silent > 1_000 ? silent : 0);
}

let lastAge: { symbol: string; ms: number } | null = null;

/** The last Level 2 age the Trade screen measured since this page opened, for Settings' link card; null before any. */
export function lastLevel2Age(): { symbol: string; ms: number } | null {
  return lastAge;
}

/** `level2AgeMs`, read once a second for a header. */
export function useLevel2Age(symbol: string | null): number | null {
  const [age, setAge] = useState<number | null>(null);
  useEffect(() => {
    if (!symbol) {
      setAge(null);
      return undefined;
    }
    const read = (): void => {
      const ms = level2AgeMs(symbol);
      if (ms != null) lastAge = { symbol, ms };
      setAge(ms);
    };
    read();
    const timer = window.setInterval(read, 1_000);
    return () => window.clearInterval(timer);
  }, [symbol]);
  return age;
}

function bookWhyOf(depth: ReturnType<typeof useIbkrDepth>): string | null {
  if (depth.lent) return depthLentText(depth.lent);
  if (depth.error) return depth.error;
  if (depth.book?.l1_fallback) return 'IBKR sent no Level 2 for this stock: this is the top of book only.';
  return null;
}

export function usePhoneTrade(symbol: string): PhoneTrade {
  const session = usePhoneSession();
  const status = useIbkrStatus();
  const account = useIbkrAccountContext();
  const depth = useIbkrDepth(symbol, true);
  const tape = useIbkrTape(symbol, true);
  const lag = useViewLock(symbol);
  const botsQty = useBotsQty(symbol);

  const book = depth.book;
  const bid = book?.bids[0]?.price ?? null;
  const ask = book?.asks[0]?.price ?? null;
  const depthSubscribed = book != null && depth.connected;
  const position = useMemo(() => findOpenIbkrPosition(account.positions, symbol), [account.positions, symbol]);
  const accountError = account.error ?? (account.stale ? 'The account on screen is not current.' : null);

  // The runtime the desk's hotkeys run with (hotkeys/NovaActionRuntimeSync), from the same readers.
  const runtime = useMemo<NovaActionRuntime>(() => ({
    symbol,
    connected: Boolean(status.connected),
    spendStatus: status.spend_status,
    accountMode: status.mode,
    accountError,
    position,
    botsQty,
    topOfBook: { symbol, bid, ask, depthSubscribed },
    // One tap is the order: the phone's ticket shows what a button sends on the button.
    requestConfirm: () => Promise.resolve(true),
  }), [symbol, status.connected, status.spend_status, status.mode, accountError, position, botsQty, bid, ask, depthSubscribed]);

  const { order } = session;
  const act = useCallback((label: string, action: NovaActionRecord, how: 'sent' | 'done' = 'sent') => {
    order(label, async (): Promise<TicketAnswer> => {
      const result = await runNovaAction(action, runtime);
      return { ok: result.ok, text: result.text };
    }, how);
  }, [order, runtime]);

  const place = useCallback((label: string, payload: ManualOrderPayload, referencePrice?: number | null) => {
    order(label, async (): Promise<TicketAnswer> => {
      const result = await placeIbkrOrder(payload, newGestureKey('phone_ticket'), { referencePrice });
      return { ok: result.ok, text: result.ok ? `Order #${String(result.order_id ?? '?')} placed` : result.error ?? 'The desk refused the order.' };
    });
  }, [order]);

  const working = account.orders;
  const workingHere = useMemo(() => working.filter((o) => o.symbol.toUpperCase() === symbol), [working, symbol]);

  return {
    symbol,
    book,
    bookWhy: bookWhyOf(depth),
    tape,
    bid,
    ask,
    position,
    heldQty: position?.qty ?? 0,
    accountCurrent: !account.loading && !account.error && !account.stale,
    working,
    workingHere,
    lag,
    armed: session.armed,
    act,
    place,
  };
}
