/**
 * One Trader tab's Who trades switch (ADR 037): the stock's view, read every `STOCK_MODE_POLL_MS` while
 * the tab shows live; the writes behind the switch and the plan card; this tab's memory of the
 * position; and the moment the chart shows, with its one ping per call. Nothing is read on a replay
 * desk or the sample desk.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { DepthMarker } from '../ibkr';
import { STOCK_MODE_PATH, STOCK_MODE_POLL_MS } from './constants';
import { momentOf, NO_HELD, nextHeld, type HeldMemory, type Moment, type MomentInputs } from './momentModel';
import { sizeFor } from './planMath';
import type { StockModeView, StockRead, StockSide } from './types';
import { usePolledRead } from './useStockRead';
import { approvePlan, putStockMode, takeOverExit, withdrawApproval } from './whoTradesApi';
import { level2Markers, orderLevels, type OrderLevels } from './whoTradesModel';
import { normalizeStockMode } from './whoTradesNormalize';
import { pingCall } from './whoTradesSound';

/** The clock the moment reads: calls that last seconds (ENTER NOW, what Nova just did) need it. */
const MOMENT_TICK_MS = 1_000;

export interface WhoTradesState {
  view: StockModeView | null;
  loading: boolean;
  /** An API from before ADR 037 answers no view. */
  unavailable: boolean;
  /** The poll's trouble, or the last write's refusal. */
  error: string | null;
  /** What is being saved now; null when nothing is. */
  busy: string | null;
  moment: Moment | null;
  levels: OrderLevels | null;
  markers: DepthMarker[];
  /** The moment's inputs without its clock: what the plan card's buttons and the switch's locks read. */
  inputs: MomentInputs;
  setSides: (buy: StockSide, sell: StockSide) => Promise<void>;
  /** Approve the plan: at the trigger, or `now` on a triggered setup. */
  approve: (now: boolean) => Promise<void>;
  withdraw: () => Promise<void>;
  takeOver: () => Promise<void>;
}

interface Options {
  symbol: string;
  live: boolean;
  read: StockRead | null;
  riskUsd: number;
  position: { qty: number; avgCost: number | null } | null;
  last: number | null;
}

function useNow(on: boolean): number {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    if (!on) return;
    setNow(Date.now() / 1000);
    const id = window.setInterval(() => setNow(Date.now() / 1000), MOMENT_TICK_MS);
    return () => window.clearInterval(id);
  }, [on]);
  return now;
}

/** Keep one object while its content is the same, so consumers redraw only on a change. */
function useStable<T>(value: T): T {
  const ref = useRef(value);
  const key = JSON.stringify(value);
  const last = useRef(key);
  if (key !== last.current) {
    last.current = key;
    ref.current = value;
  }
  return ref.current;
}

export function useWhoTrades({ symbol, live, read, riskUsd, position, last }: Options): WhoTradesState {
  const sym = symbol.trim().toUpperCase();
  const polled = usePolledRead({
    url: sym ? `${STOCK_MODE_PATH}/${encodeURIComponent(sym)}` : null,
    resetKey: sym,
    normalize: normalizeStockMode,
    pollMs: STOCK_MODE_POLL_MS,
    active: live,
    what: 'Who trades read',
    accept: v => v.symbol === sym,
  });
  // A write answers the new view at once; the poll takes over from the next answer that is as new.
  const [written, setWritten] = useState<StockModeView | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [writeError, setWriteError] = useState<string | null>(null);
  const [held, setHeld] = useState<HeldMemory>(NO_HELD);
  useEffect(() => {
    setWritten(null);
    setWriteError(null);
    setHeld(NO_HELD);
  }, [sym]);

  const polledView = polled.data;
  const view = written && written.symbol === sym && (!polledView || written.generated_at > polledView.generated_at)
    ? written
    : polledView;
  const now = useNow(live);
  // What the rail's buttons read (no clock: a second going by redraws nothing), and the moment's view
  // of it with the clock, for the calls that last seconds.
  const inputs = useMemo<MomentInputs>(() => ({
    read: live ? read : null,
    who: live ? view : null,
    position,
    last,
    now: 0,
    riskUsd,
    held,
  }), [live, read, view, position, last, riskUsd, held]);
  const clocked = useMemo<MomentInputs>(() => ({ ...inputs, now }), [inputs, now]);

  useEffect(() => {
    if (!live) return;
    const next = nextHeld(held, clocked);
    if (next !== held) setHeld(next);
  }, [live, held, clocked]);

  const moment = useStable(live ? momentOf(clocked) : null);
  const levels = useStable(live ? orderLevels(inputs) : null);
  const markers = useStable(level2Markers(levels));

  const call = moment?.call ?? null;
  useEffect(() => {
    if (call?.ping) pingCall(call.id, call.tone);
  }, [call]);

  const run = useCallback(async (what: string, fn: () => Promise<StockModeView>) => {
    setBusy(what);
    setWriteError(null);
    try {
      setWritten(await fn());
    } catch (e) {
      setWriteError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }, []);

  const setSides = useCallback(
    (buy: StockSide, sell: StockSide) => run('Saving who trades…', () => putStockMode(sym, buy, sell, riskUsd)),
    [run, sym, riskUsd],
  );
  const plan = read?.plan ?? null;
  const approve = useCallback((now: boolean) => {
    const qty = plan ? sizeFor(riskUsd, plan.risk) : null;
    if (!plan || plan.setup_id === null || plan.entry === null || plan.stop === null || plan.target === null || qty === null) {
      setWriteError('The plan has nothing to approve.');
      return Promise.resolve();
    }
    return run(now ? 'Sending the buy…' : 'Approving…', () => approvePlan(sym, {
      setup_id: plan.setup_id as string, entry: plan.entry as number, stop: plan.stop as number,
      target: plan.target as number, qty, now,
    }));
  }, [run, sym, plan, riskUsd]);
  const withdraw = useCallback(() => run('Cancelling…', () => withdrawApproval(sym)), [run, sym]);
  const takeOver = useCallback(() => run('Taking over the exit…', () => takeOverExit(sym, riskUsd)), [run, sym, riskUsd]);

  return useMemo(() => ({
    view,
    loading: polled.loading && !view,
    unavailable: polled.unavailable,
    error: writeError ?? polled.error,
    busy,
    moment,
    levels,
    markers,
    inputs,
    setSides,
    approve,
    withdraw,
    takeOver,
  }), [view, polled.loading, polled.unavailable, polled.error, writeError, busy, moment, levels, markers, inputs,
    setSides, approve, withdraw, takeOver]);
}
