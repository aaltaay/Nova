/**
 * One Trader tab's stock read (ADR 036): the polled read, the day's setups that ended, the operator's
 * own plan, the venue sleeve's risk per trade, what the charts draw, the sheet and a chart focus -- shared
 * by the plan box on the rail, the tiles, the sheet over the charts and every chart pane's drawings. The read
 * places nothing; "Stage in ticket" only fills the tab's ticket. Who trades the stock (ADR 037) rides along:
 * the switch's view and writes, the moment on the chart and the plan's rows in Level 2.
 */
import { useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import { parseRiskUsd, saveSleeveRisk, useSleeveRisk, venueOrNull, type SleeveRisk } from '../setups';
import { tickerLastTrade } from '../hooks/tickerStore';
import { useSimAccountClock } from '../practice';
import { useTickerSelect } from '../hooks/useTickerStream';
import { hmrStableContext } from '../utils/hmrStableContext';
import { readPref, writePref } from '../utils/prefStore';
import { STOCK_READ_LAYERS_KEY } from './constants';
import { pastNowOf, type PastSetups } from './pastSetups';
import type { LabelDetail } from './sceneLabels';
import type { DecisionEvent, ReadGroupId, StockDecisions, StockHistory, StockRead } from './types';
import {
  useStockRead,
  useStockReadDecisions,
  useStockReadHistory,
  useStockReadPast,
  type PolledState,
} from './useStockRead';
import { useHeldTrade, type FlushReading, type HeldTrack } from './useHeldTrade';
import { useWhoTrades, type WhoTradesState } from './useWhoTrades';

export type SheetTab = 'signals' | 'decisions' | 'history';

/** The read a tab may draw and plan on (ADR 052): this desk's -- a read from the other side of the live edge (the
 * clock just moved) is not -- and on a replay never one made at a later playhead than `simNow` (a rewind shown
 * before the next read). Pure. */
export function readNowOf(read: StockRead | null, replay: boolean, simNow: number | null): StockRead | null {
  if (!read || read.replay !== replay) return null;
  return replay && simNow !== null && read.generated_at > simNow + 1 ? null : read;
}

export interface StockReadLayers {
  /** Eyes (ADR 044): everything Nova draws on the tab's charts, on or off; `setups` and `levels` are its parts. */
  eyes: boolean;
  /** The setups' shapes and the plan's levels on the charts. */
  setups: boolean;
  /** High of day, premarket high, the open and the round numbers. */
  levels: boolean;
  /** The day's setups that ended, drawn faint where they happened on the 1-minute pane. */
  past: boolean;
  /** How much their labels say: a few words (`compact`) or the whole label where it fits (`full`). */
  labels: LabelDetail;
  /** Setup types whose shapes the operator switched off. */
  hidden: string[];
  /** The plan box: whole when the card has room (`auto`), or as the operator last set it. */
  plan: 'auto' | 'open' | 'folded';
}

export interface ChartFocus {
  ts: number;
  nonce: number;
  event: DecisionEvent | null;
}

export interface StockReadContextValue {
  symbol: string;
  active: boolean;
  /** The desk replays another moment (ADR 052): the read is the replay's at the playhead -- the Sim eyes'
   * setups, the plan, the replay's levels and the setups that ended up to the playhead (#815) -- and the reads of
   * whole days (decisions, history) are not made. */
  replay: boolean;
  read: PolledState<StockRead>;
  /** The read the charts draw: this desk's (a replay's on a replay desk), and on a replay never one from after the
   * playhead -- a rewind waits for the next read instead of showing what came later (ADR 052). */
  readNow: StockRead | null;
  history: PolledState<StockHistory>;
  decisions: PolledState<StockDecisions>;
  /** The day's setups that ended and what price did next (read while the chart draws them). */
  past: PolledState<PastSetups>;
  /** The 5-minute lanes' setups that ended (the 5-minute chart's); absent outside a live Trader tab. */
  past5?: PolledState<PastSetups>;
  /** The past setups the charts draw and the legend counts: this desk's, and on a replay never read at a later
   * playhead than the tab shows (`pastNowOf`). */
  pastNow?: PastSetups | null;
  past5Now?: PastSetups | null;
  /** The operator's own plan; `side` short is a hand short (ADR 048): its buy stop over the entry. */
  manual: ManualPlan;
  /** Sets the hand plan; without `side` it keeps the plan's side, and clearing it (`entry` null) is long again. */
  setManualPlan: (entry: number | null, stop: number | null, side?: 'long' | 'short') => void;
  /** The venue sleeve's risk per trade (else the stated fallback): sizes the operator's own buys. */
  riskUsd: number;
  /** Saves it into the venue's sleeve: Nova's automatic buys size by it too. */
  setRiskUsd: (usd: number) => void;
  /** Where the risk per trade comes from, and any trouble reading or saving it. */
  risk: SleeveRisk;
  /** What the charts draw: off with Eyes off, without the parts the operator switched off, and without
   *  a strategy at Off on the Bots page (ADR 044). */
  layers: StockReadLayers;
  /** What the operator set (the toolbar's own state): Eyes, Setups and Levels as remembered. */
  prefs: StockReadLayers;
  setLayers: (patch: Partial<StockReadLayers>) => void;
  toggleLane: (setupType: string) => void;
  sheet: { open: boolean; tab: SheetTab; group: ReadGroupId | null };
  openSheet: (tab: SheetTab, group?: ReadGroupId | null) => void;
  closeSheet: () => void;
  focus: ChartFocus | null;
  focusAt: (ts: number, event?: DecisionEvent | null) => void;
  /** Back to now: the 1-minute pane scrolls to its live edge. */
  clearFocus: () => void;
  topOfBook: { bid: number | null; ask: number | null } | null;
  /** Who trades the stock (ADR 037). */
  who: WhoTradesState;
  /** The trade you hold (ADR 036 amendment 2026-10-01): the stop you set for it (never an order). */
  held: { track: HeldTrack; setStop: (stop: number | null) => void };
  /** Trial T1's tape reading while you hold, read every second. */
  flush: PolledState<FlushReading>;
  /** "Nova takes the exit": its sheet over the plan box. */
  exitSheet: { open: boolean; setOpen: (open: boolean) => void };
  /** The account's position in the stock on the desk's venue; null when none (Level 2's LIQ chip). */
  position: TabPosition | null;
}

export interface ManualPlan {
  entry: number | null;
  stop: number | null;
  side: 'long' | 'short';
}

const NO_MANUAL: ManualPlan = { entry: null, stop: null, side: 'long' };

/** The account's position in the tab's stock, as the rail knows it. */
export interface TabPosition {
  qty: number;
  avgCost: number | null;
  /** Where IBKR would liquidate it (ADR 048), and the margin it is measured by; null when not known. */
  liquidationPrice?: number | null;
  liquidationSource?: string | null;
  /** The stop order resting at the broker that protects it (`protectiveStop`); null when none. */
  workingStop?: number | null;
}

const DEFAULT_LAYERS: StockReadLayers = {
  eyes: true, setups: true, levels: true, past: true, labels: 'compact', hidden: [], plan: 'auto',
};

export function parseLayers(raw: unknown): StockReadLayers | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
  const r = raw as Record<string, unknown>;
  return {
    eyes: r.eyes !== false,          // added 2026-10-01 (ADR 044): on unless switched off
    setups: r.setups !== false,
    levels: r.levels !== false,
    past: r.past !== false,          // added 2026-09-29: a value stored before it shows them
    labels: r.labels === 'full' ? 'full' : 'compact',   // added 2026-09-30: compact unless set to full
    hidden: Array.isArray(r.hidden) ? r.hidden.filter((x): x is string => typeof x === 'string') : [],
    plan: r.plan === 'open' || r.plan === 'folded' ? r.plan : 'auto',
  };
}

/** What the charts draw from what the operator set: Eyes off draws nothing of Nova's, and a strategy at Off
 *  on the Bots page is hidden like a lane the operator switched off. */
export function drawnLayers(prefs: StockReadLayers, offStrategies: readonly string[]): StockReadLayers {
  const hidden = [...prefs.hidden, ...offStrategies.filter(s => !prefs.hidden.includes(s))];
  return {
    ...prefs,
    setups: prefs.eyes && prefs.setups,
    levels: prefs.eyes && prefs.levels,
    past: prefs.eyes && prefs.past,
    hidden,
  };
}

const StockReadCtx = hmrStableContext<StockReadContextValue>(import.meta.hot, 'StockReadContext');

export function StockReadProvider({
  symbol,
  active,
  replay,
  topOfBook,
  position = null,
  venue = null,
  children,
}: {
  symbol: string;
  active: boolean;
  replay: boolean;
  topOfBook: { symbol: string; bid: number | null; ask: number | null } | null;
  /** The account's position in this stock on the desk's venue; null when none. */
  position?: TabPosition | null;
  /** The desk venue (live | paper | sim): Who trades is the venue's own (#657). */
  venue?: string | null;
  children: ReactNode;
}) {
  const sym = symbol.trim().toUpperCase();
  const sample = useSampleDataOptional();
  // The tab's live last trade, read here (#707): it renders this provider on a print; the value it gives
  // its readers changes only when what they show does (useWhoTrades keeps the price to itself).
  const lastPrice = useTickerSelect(sym, (state) => tickerLastTrade(state, sym)?.price ?? null);
  const [manual, setManual] = useState<ManualPlan>(NO_MANUAL);
  const [layers, setLayerState] = useState(() => readPref(STOCK_READ_LAYERS_KEY, DEFAULT_LAYERS, parseLayers));
  const [sheet, setSheet] = useState<StockReadContextValue['sheet']>({ open: false, tab: 'signals', group: null });
  const [focus, setFocus] = useState<ChartFocus | null>(null);

  useEffect(() => {
    setManual(NO_MANUAL);
    setFocus(null);
  }, [sym]);

  const live = active && !replay;
  // The read and who trades answer on a Sim replay too: the backend reads the replay at the playhead there.
  const readable = active;
  const simNow = useSimAccountClock(replay && readable).nowTs;
  const sleeveVenue = venueOrNull(venue);
  const risk = useSleeveRisk(sleeveVenue, readable && !sample);
  const riskUsd = risk.riskUsd;
  const posQty = position?.qty ?? null;
  const posCost = position?.avgCost ?? null;
  const posLiq = position?.liquidationPrice ?? null;
  const posLiqSource = position?.liquidationSource ?? null;
  const posStop = position?.workingStop ?? null;
  const pos = useMemo(() => (posQty === null ? null : { qty: posQty, avgCost: posCost }), [posQty, posCost]);
  const tabPosition = useMemo<TabPosition | null>(
    () => (posQty === null ? null : { qty: posQty, avgCost: posCost, liquidationPrice: posLiq,
      liquidationSource: posLiqSource, workingStop: posStop }),
    [posQty, posCost, posLiq, posLiqSource, posStop],
  );
  // The held query needs the last read (its plan and stop); the read needs the query: the last answer drives it.
  const [lastRead, setLastRead] = useState<StockRead | null>(null);
  const heldTrade = useHeldTrade({ symbol: sym, live: live && !sample, position: pos, read: lastRead,
    workingStop: posStop });
  // On a replay the read follows the playhead: a new 5 s of it -- forward, or back on a rewind -- reads at once.
  const nudge = replay && simNow !== null ? String(Math.floor(simNow / 5)) : undefined;
  const read = useStockRead(sym, { active: readable, entry: manual.entry, stop: manual.stop, side: manual.side,
    held: heldTrade.query, nudge });
  useEffect(() => setLastRead(read.data), [read.data]);
  const [exitOpen, setExitOpen] = useState(false);
  useEffect(() => setExitOpen(false), [sym]);
  const history = useStockReadHistory(sym, live);
  const decisions = useStockReadDecisions(sym, live && sheet.open && sheet.tab === 'decisions');
  // The lanes' drawn states: a setup that fails or ends is read as past at once, not at the next poll.
  const lanes = read.data?.setups;
  // A strategy at Off on the Bots page draws nothing (ADR 044): its lane's own level is 0 -- the 5-minute flat
  // top's too (a strategy since 2026-10-06); the built-in 5-minute lanes are no strategy and come in `setups_5m`.
  const offKey = (lanes ?? []).filter(l => l.level === 0).map(l => l.setup_type).join('|');
  const drawn = useMemo(() => drawnLayers(layers, offKey ? offKey.split('|') : []), [layers, offKey]);
  const laneKey = useMemo(() => (lanes ?? []).map(l => `${l.setup_type}:${l.state}:${l.leg?.t ?? ''}`).join('|'), [lanes]);
  // On a replay the setups that ended are the Sim eyes' up to the playhead (#815): read again with the playhead too.
  const pastNudge = nudge ? `@${nudge}` : '';
  const past = useStockReadPast(sym, readable && drawn.setups && drawn.past, laneKey + pastNudge);
  const lanes5 = read.data?.setups_5m;
  const laneKey5 = useMemo(() => [...(lanes5 ?? []), ...(lanes ?? []).filter(l => l.timeframe === '5m')]
    .map(l => `${l.setup_type}:${l.state}:${l.leg?.t ?? ''}`).join('|'), [lanes5, lanes]);
  const past5 = useStockReadPast(sym, readable && drawn.setups && drawn.past, laneKey5 + pastNudge, '5m');
  const pastNow = pastNowOf(past.data, sym, replay, simNow);
  const past5Now = pastNowOf(past5.data, sym, replay, simNow);
  const ownRead = readNowOf(read.data, replay, simNow);
  const who = useWhoTrades({
    symbol: sym, live: readable && !sample, read: ownRead, riskUsd, ttlSec: risk.ttlSec, position: pos,
    last: lastPrice, venue,
    flush: live ? heldTrade.flush.data : null,
    clockNow: replay ? simNow : null,
  });

  const setManualPlan = useCallback((entry: number | null, stop: number | null, side?: 'long' | 'short') => {
    setManual(prev => {
      const e = entry !== null && entry > 0 ? entry : null;
      return { entry: e, stop: stop !== null && stop > 0 ? stop : null, side: e === null ? 'long' : side ?? prev.side };
    });
  }, []);
  const setRiskUsd = useCallback((usd: number) => {
    const next = parseRiskUsd(usd);
    if (next === null) return;
    void saveSleeveRisk(next, sleeveVenue);
  }, [sleeveVenue]);
  const setLayers = useCallback((patch: Partial<StockReadLayers>) => {
    setLayerState(prev => {
      const next = { ...prev, ...patch };
      writePref(STOCK_READ_LAYERS_KEY, next);
      return next;
    });
  }, []);
  const toggleLane = useCallback((setupType: string) => {
    setLayerState(prev => {
      const hidden = prev.hidden.includes(setupType)
        ? prev.hidden.filter(x => x !== setupType)
        : [...prev.hidden, setupType];
      const next = { ...prev, hidden };
      writePref(STOCK_READ_LAYERS_KEY, next);
      return next;
    });
  }, []);
  const openSheet = useCallback((tab: SheetTab, group: ReadGroupId | null = null) => {
    setSheet({ open: true, tab, group });
  }, []);
  const closeSheet = useCallback(() => setSheet(s => ({ ...s, open: false })), []);
  const focusAt = useCallback((ts: number, event: DecisionEvent | null = null) => {
    setFocus(prev => ({ ts, event, nonce: (prev?.nonce ?? 0) + 1 }));
  }, []);
  const clearFocus = useCallback(() => setFocus(null), []);

  // This tab's own book only: another symbol's top of book is not this plan's ask.
  const ours = topOfBook !== null && topOfBook.symbol.toUpperCase() === sym;
  const tobBid = ours ? topOfBook.bid : null;
  const tobAsk = ours ? topOfBook.ask : null;
  const book = useMemo(() => (ours ? { bid: tobBid, ask: tobAsk } : null), [ours, tobBid, tobAsk]);

  const value = useMemo<StockReadContextValue>(() => ({
    symbol: sym,
    active,
    replay,
    read,
    readNow: ownRead,
    history,
    decisions,
    past,
    past5,
    pastNow,
    past5Now,
    manual,
    setManualPlan,
    riskUsd,
    setRiskUsd,
    risk,
    layers: drawn,
    prefs: layers,
    setLayers,
    toggleLane,
    sheet,
    openSheet,
    closeSheet,
    focus,
    focusAt,
    clearFocus,
    topOfBook: book,
    who,
    held: { track: heldTrade.track, setStop: heldTrade.setStop },
    flush: heldTrade.flush,
    exitSheet: { open: exitOpen, setOpen: setExitOpen },
    position: tabPosition,
  }), [sym, active, replay, read, ownRead, history, decisions, past, past5, pastNow, past5Now, manual, setManualPlan,
    riskUsd, setRiskUsd, risk,
    layers, drawn, setLayers, toggleLane, sheet, openSheet, closeSheet, focus, focusAt, clearFocus, book, who,
    heldTrade.track, heldTrade.setStop, heldTrade.flush, exitOpen, tabPosition]);

  // The sample desk reads nothing live: no read, so no rail block, sheet or drawings.
  if (sample) return <>{children}</>;
  return <StockReadCtx.Provider value={value}>{children}</StockReadCtx.Provider>;
}

/** The tab's stock read; null outside a Trader tab (the rail and panes then draw nothing). */
export function useStockReadContext(): StockReadContextValue | null {
  return useContext(StockReadCtx) ?? null;
}
