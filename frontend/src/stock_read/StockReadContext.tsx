/**
 * One Trader tab's stock read (ADR 036): the polled read, the operator's own plan, their risk per
 * trade, what the charts draw, the sheet and a chart focus -- shared by the plan box on the rail,
 * the tiles, the sheet over the charts and every chart pane's drawings. Read-only: nothing here
 * places an order; "Stage in ticket" only fills the tab's ticket.
 */
import { useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import { hmrStableContext } from '../utils/hmrStableContext';
import { readPref, writePref } from '../utils/prefStore';
import {
  STOCK_READ_LAYERS_KEY,
  STOCK_READ_RISK_DEFAULT_USD,
  STOCK_READ_RISK_KEY,
} from './constants';
import { parseRiskUsd } from './planMath';
import type { DecisionEvent, ReadGroupId, StockDecisions, StockHistory, StockRead } from './types';
import {
  useStockRead,
  useStockReadDecisions,
  useStockReadHistory,
  type PolledState,
} from './useStockRead';

export type SheetTab = 'signals' | 'decisions' | 'history';

export interface StockReadLayers {
  /** The setups' shapes and the plan's levels on the charts. */
  setups: boolean;
  /** High of day, premarket high, the open and the half dollars. */
  levels: boolean;
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
  /** The desk replays another moment: the read is today's live stock, so nothing is drawn. */
  replay: boolean;
  read: PolledState<StockRead>;
  history: PolledState<StockHistory>;
  decisions: PolledState<StockDecisions>;
  manual: { entry: number | null; stop: number | null };
  setManualPlan: (entry: number | null, stop: number | null) => void;
  riskUsd: number;
  setRiskUsd: (usd: number) => void;
  layers: StockReadLayers;
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
}

const DEFAULT_LAYERS: StockReadLayers = { setups: true, levels: true, hidden: [], plan: 'auto' };

export function parseLayers(raw: unknown): StockReadLayers | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
  const r = raw as Record<string, unknown>;
  return {
    setups: r.setups !== false,
    levels: r.levels !== false,
    hidden: Array.isArray(r.hidden) ? r.hidden.filter((x): x is string => typeof x === 'string') : [],
    plan: r.plan === 'open' || r.plan === 'folded' ? r.plan : 'auto',
  };
}

const StockReadCtx = hmrStableContext<StockReadContextValue>(import.meta.hot, 'StockReadContext');

export function StockReadProvider({
  symbol,
  active,
  replay,
  topOfBook,
  children,
}: {
  symbol: string;
  active: boolean;
  replay: boolean;
  topOfBook: { symbol: string; bid: number | null; ask: number | null } | null;
  children: ReactNode;
}) {
  const sym = symbol.trim().toUpperCase();
  const sample = useSampleDataOptional();
  const [manual, setManual] = useState<{ entry: number | null; stop: number | null }>({ entry: null, stop: null });
  const [riskUsd, setRiskState] = useState(() => readPref(STOCK_READ_RISK_KEY, STOCK_READ_RISK_DEFAULT_USD, parseRiskUsd));
  const [layers, setLayerState] = useState(() => readPref(STOCK_READ_LAYERS_KEY, DEFAULT_LAYERS, parseLayers));
  const [sheet, setSheet] = useState<StockReadContextValue['sheet']>({ open: false, tab: 'signals', group: null });
  const [focus, setFocus] = useState<ChartFocus | null>(null);

  useEffect(() => {
    setManual({ entry: null, stop: null });
    setFocus(null);
  }, [sym]);

  const live = active && !replay;
  const read = useStockRead(sym, { active: live, entry: manual.entry, stop: manual.stop });
  const history = useStockReadHistory(sym, live);
  const decisions = useStockReadDecisions(sym, live && sheet.open && sheet.tab === 'decisions');

  const setManualPlan = useCallback((entry: number | null, stop: number | null) => {
    setManual({ entry: entry !== null && entry > 0 ? entry : null, stop: stop !== null && stop > 0 ? stop : null });
  }, []);
  const setRiskUsd = useCallback((usd: number) => {
    const next = parseRiskUsd(usd);
    if (next === null) return;
    setRiskState(next);
    writePref(STOCK_READ_RISK_KEY, next);
  }, []);
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
    history,
    decisions,
    manual,
    setManualPlan,
    riskUsd,
    setRiskUsd,
    layers,
    setLayers,
    toggleLane,
    sheet,
    openSheet,
    closeSheet,
    focus,
    focusAt,
    clearFocus,
    topOfBook: book,
  }), [sym, active, replay, read, history, decisions, manual, setManualPlan, riskUsd, setRiskUsd, layers, setLayers,
    toggleLane, sheet, openSheet, closeSheet, focus, focusAt, clearFocus, book]);

  // The sample desk reads nothing live: no read, so no rail block, sheet or drawings.
  if (sample) return <>{children}</>;
  return <StockReadCtx.Provider value={value}>{children}</StockReadCtx.Provider>;
}

/** The tab's stock read; null outside a Trader tab (the rail and panes then draw nothing). */
export function useStockReadContext(): StockReadContextValue | null {
  return useContext(StockReadCtx) ?? null;
}
