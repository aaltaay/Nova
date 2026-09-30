/**
 * Publishes L2 top-of-book for the open symbol so Ask±/Bid± Nova Actions
 * never silently substitute last trade.
 */

import {
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { hmrStableContext } from '../utils/hmrStableContext';
import { useRenderCount } from '../perf/useRenderCount';

export interface TopOfBook {
  symbol: string;
  bid: number | null;
  ask: number | null;
  /** True when a depth subscription is active for this symbol. */
  depthSubscribed: boolean;
}

interface TopOfBookContextValue {
  topOfBook: TopOfBook | null;
  setTopOfBook: (next: TopOfBook | null) => void;
}

const TopOfBookContext = hmrStableContext<TopOfBookContextValue>(import.meta.hot, 'TopOfBookContext');

/** Same symbol, bid, ask and depth line: nothing a reader of the top of book can see changed. */
export function sameTopOfBook(a: TopOfBook | null, b: TopOfBook | null): boolean {
  if (a === b) return true;
  if (a === null || b === null) return false;
  return a.symbol === b.symbol && a.bid === b.bid && a.ask === b.ask && a.depthSubscribed === b.depthSubscribed;
}

export function TopOfBookProvider({ children }: { children: ReactNode }) {
  useRenderCount('TopOfBookProvider');
  const [topOfBook, setTopOfBookState] = useState<TopOfBook | null>(null);
  // The ladder publishes on every book (about 17 a second on a busy name) while the best bid and
  // ask change far less often: keep the old object then, so every reader (the whole Trader page
  // among them) is not rendered again for nothing.
  const setTopOfBook = useCallback((next: TopOfBook | null) => {
    setTopOfBookState(prev => (sameTopOfBook(prev, next) ? prev : next));
  }, []);
  const value = useMemo(
    () => ({ topOfBook, setTopOfBook }),
    [topOfBook, setTopOfBook],
  );
  return (
    <TopOfBookContext.Provider value={value}>{children}</TopOfBookContext.Provider>
  );
}

export function useTopOfBook(): TopOfBookContextValue {
  const ctx = useContext(TopOfBookContext);
  if (!ctx) {
    return {
      topOfBook: null,
      setTopOfBook: () => undefined,
    };
  }
  return ctx;
}
