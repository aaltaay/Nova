/**
 * One Trader tab's trade moment (ADR 037): the moment the 1-minute chart shows, with its one ping per call; the
 * plan's levels the charts and Level 2 draw; and this tab's memory of the operator's position. It reads nothing
 * itself -- the read, the position and the tape's readings come in -- and nothing is computed on the sample desk.
 * On a Sim replay the moment runs on the playhead (`clockNow`, ADR 052). Nova places nothing: who trades the stock
 * is the operator (ADR 072).
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import type { DepthMarker } from '../ibkr';
import type { BigWalls } from './bigSeller';
import { heldMarkers } from './heldView';
import { NO_HELD, type HeldMemory, type Moment, type MomentInputs } from './momentModel';
import { momentOfSides, nextHeldSides } from './momentShort';
import { pingCall } from './momentSound';
import { level2Markers, orderLevels, type OrderLevels } from './tradeLevels';
import type { StockRead } from './types';
import type { FlushReading } from './useHeldTrade';

/** The clock the moment reads: calls that last seconds (ENTER NOW) need it. */
const MOMENT_TICK_MS = 1_000;

export interface TradeMomentState {
  moment: Moment | null;
  levels: OrderLevels | null;
  markers: DepthMarker[];
  /** The moment's inputs without its clock or the live price (`last` is null): what the plan card's buttons
   * read. The price changes on every print; a reader that needs it reads the ticker (#707). */
  inputs: MomentInputs;
}

interface Options {
  symbol: string;
  live: boolean;
  read: StockRead | null;
  /** The venue sleeve's risk per trade: sizes the operator's own buys. */
  riskUsd: number;
  position: { qty: number; avgCost: number | null } | null;
  last: number | null;
  /** The desk venue (live | paper | sim), or null when the status names none. */
  venue?: string | null;
  /** Trial T1's tape reading while you hold. */
  flush?: FlushReading | null;
  /** The big sellers and buyers on the held Level 2 line (#846); null when unread. */
  big?: BigWalls | null;
  /** The clock the moment reads instead of the wall's: the Sim playhead on a replay (epoch seconds). */
  clockNow?: number | null;
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

export function useTradeMoment({
  symbol, live, read, riskUsd, position, last, venue = null, flush = null, big = null, clockNow,
}: Options): TradeMomentState {
  const sym = symbol.trim().toUpperCase();
  const [held, setHeld] = useState<HeldMemory>(NO_HELD);
  // A new stock or a venue change starts the position's memory again: the old venue's position is not this one.
  useEffect(() => setHeld(NO_HELD), [sym, venue]);

  const wall = useNow(live && clockNow == null);
  const now = clockNow ?? wall;
  // What the rail's buttons read (no clock: a second going by redraws nothing), and the moment's view
  // of it with the clock, for the calls that last seconds.
  // The rail reads `base`, which has no price: a new object on every print rendered every reader of the
  // stock read -- the chart layers, their keys, the plan -- about 20 times a second (#707).
  const base = useMemo<MomentInputs>(() => ({
    read: live ? read : null,
    venue,
    position,
    last: null,
    now: 0,
    riskUsd,
    held,
    flush: flush ? { at: flush.at, score: flush.score, label: flush.label } : null,
    big,
  }), [live, read, venue, position, riskUsd, held, flush, big]);
  const inputs = useMemo<MomentInputs>(() => ({ ...base, last }), [base, last]);
  const clocked = useMemo<MomentInputs>(() => ({ ...inputs, now }), [inputs, now]);

  useEffect(() => {
    if (!live) return;
    const next = nextHeldSides(held, clocked);
    if (next !== held) setHeld(next);
  }, [live, held, clocked]);

  const moment = useStable(live ? momentOfSides(clocked) : null);
  const levels = useStable(live ? orderLevels(inputs) : null);
  // While you hold: NEXT with the asks and your STOP with the bids (the read's own view of the position).
  const markers = useStable(live && read?.held ? heldMarkers(read.held) : level2Markers(levels, read?.plan?.side));

  const call = moment?.call ?? null;
  useEffect(() => {
    if (call?.ping) pingCall(call.id, call.tone);
  }, [call]);

  return useMemo(() => ({ moment, levels, markers, inputs: base }), [moment, levels, markers, base]);
}
