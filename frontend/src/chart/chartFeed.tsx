/** Where a pane's candles come from. The default is the live desk. /review supplies a recorded day. */

import { createContext, useCallback, useContext, useState, type ReactNode } from 'react';
import type { RawBar } from '../tickerChartData';

export type RecordedChartFeed = {
  kind: 'recorded';
  symbol: string;
  date: string;
  asOfIso: string;
  source: 'front-door' | 'fixture';
  bars: Partial<Record<'10Sec' | '1Min' | '5Min' | '1Day', RawBar[]>>;
  vwapBars: RawBar[];
};

export type ChartFeed = { kind: 'live' } | RecordedChartFeed;

const LIVE: ChartFeed = { kind: 'live' };
const FeedContext = createContext<ChartFeed>(LIVE);
const PaintContext = createContext<((id: string) => void) | null>(null);

type ClearApi = { token: number; clear: () => void };
const ClearContext = createContext<ClearApi>({ token: 0, clear: () => {} });

export function ChartFeedProvider({
  feed,
  onPanePainted,
  children,
}: {
  feed: ChartFeed;
  onPanePainted?: (id: string) => void;
  children: ReactNode;
}) {
  const [token, setToken] = useState(0);
  const clear = useCallback(() => setToken((value) => value + 1), []);
  return (
    <FeedContext.Provider value={feed}>
      <PaintContext.Provider value={onPanePainted ?? null}>
        <ClearContext.Provider value={{ token, clear }}>{children}</ClearContext.Provider>
      </PaintContext.Provider>
    </FeedContext.Provider>
  );
}

export function useChartFeed(): ChartFeed {
  return useContext(FeedContext);
}

export function useReportPanePainted(): ((id: string) => void) | null {
  return useContext(PaintContext);
}

export function useRecordedClearToken(): number {
  return useContext(ClearContext).token;
}

export function useClearRecordedDrawings(): () => void {
  return useContext(ClearContext).clear;
}
