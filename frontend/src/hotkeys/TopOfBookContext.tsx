/**
 * Publishes L2 top-of-book for the open symbol so Ask±/Bid± Nova Actions
 * never silently substitute last trade.
 */

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

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

const TopOfBookContext = createContext<TopOfBookContextValue | null>(null);

export function TopOfBookProvider({ children }: { children: ReactNode }) {
  const [topOfBook, setTopOfBookState] = useState<TopOfBook | null>(null);
  const setTopOfBook = useCallback((next: TopOfBook | null) => {
    setTopOfBookState(next);
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
