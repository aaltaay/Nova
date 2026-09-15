/**
 * App-level Advise overlay. Prefill is free; Run spends OpenRouter tokens.
 */
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { useWorkspace } from '../workspace/WorkspaceContext';
import {
  fetchAdviseEstimate,
  fetchAdviseHistory,
  fetchAdviseLatest,
  postAdviseCancel,
  postAdviseRetry,
  postAdviseRun,
} from './adviseApi';
import { ADVISE_DEFAULT_DEPTH } from './constants';
import type { AdviseEstimate, AdviseRun } from './types';
import { useAdviseStream } from './useAdviseStream';

interface AdviseContextValue {
  open: boolean;
  symbol: string;
  depth: number;
  run: AdviseRun | null;
  history: AdviseRun[];
  estimate: AdviseEstimate | null;
  error: string | null;
  busy: boolean;
  openAdvise: () => void;
  closeAdvise: () => void;
  setSymbol: (value: string) => void;
  setDepth: (value: number) => void;
  loadBook: (nextSymbol?: string, nextDepth?: number) => Promise<void>;
  loadHistoryRun: (runId: number) => void;
  runDebate: (force: boolean) => Promise<void>;
  cancelDebate: () => Promise<void>;
  retryDebate: () => Promise<void>;
}

const AdviseContext = createContext<AdviseContextValue | null>(null);

function deskSymbol(
  selected: string | null,
  trader: string | null,
): string {
  return (trader || selected || '').trim().toUpperCase();
}

export function AdviseProvider({ children }: { children: ReactNode }) {
  const { selectedSymbol, activeTraderSymbol } = useWorkspace();
  const [open, setOpen] = useState(false);
  const [symbol, setSymbol] = useState('');
  const [depth, setDepth] = useState(ADVISE_DEFAULT_DEPTH);
  const [run, setRun] = useState<AdviseRun | null>(null);
  const [history, setHistory] = useState<AdviseRun[]>([]);
  const [estimate, setEstimate] = useState<AdviseEstimate | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useAdviseStream(run, setRun);

  const loadBook = useCallback(async (nextSymbol?: string, nextDepth?: number) => {
    const sym = (nextSymbol ?? symbol).trim().toUpperCase();
    const rounds = nextDepth ?? depth;
    if (!sym) {
      setRun(null);
      setHistory([]);
      setEstimate(null);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const [latest, rows, cost] = await Promise.all([
        fetchAdviseLatest(sym, rounds),
        fetchAdviseHistory(sym),
        fetchAdviseEstimate(sym, rounds),
      ]);
      setRun(latest);
      setHistory(rows);
      setEstimate(cost);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, [depth, symbol]);

  const openAdvise = useCallback(() => {
    const prefill = deskSymbol(selectedSymbol, activeTraderSymbol);
    setSymbol(prefill);
    setOpen(true);
    void loadBook(prefill, depth);
  }, [activeTraderSymbol, depth, loadBook, selectedSymbol]);

  const closeAdvise = useCallback(() => setOpen(false), []);

  const loadHistoryRun = useCallback((runId: number) => {
    const found = history.find((row) => row.id === runId);
    if (found) setRun(found);
  }, [history]);

  const runDebate = useCallback(async (force: boolean) => {
    const sym = symbol.trim().toUpperCase();
    if (!sym) {
      setError('Enter a symbol before Run');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const next = await postAdviseRun(sym, depth, force);
      setRun(next);
      const rows = await fetchAdviseHistory(sym);
      setHistory(rows);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, [depth, symbol]);

  const cancelDebate = useCallback(async () => {
    if (!run) return;
    setBusy(true);
    try {
      setRun(await postAdviseCancel(run.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, [run]);

  const retryDebate = useCallback(async () => {
    if (!run) return;
    setBusy(true);
    setError(null);
    try {
      setRun(await postAdviseRetry(run.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, [run]);

  const value = useMemo(
    () => ({
      open,
      symbol,
      depth,
      run,
      history,
      estimate,
      error,
      busy,
      openAdvise,
      closeAdvise,
      setSymbol,
      setDepth,
      loadBook,
      loadHistoryRun,
      runDebate,
      cancelDebate,
      retryDebate,
    }),
    [
      busy,
      cancelDebate,
      closeAdvise,
      depth,
      error,
      estimate,
      history,
      loadBook,
      loadHistoryRun,
      open,
      openAdvise,
      retryDebate,
      run,
      runDebate,
      symbol,
    ],
  );

  return <AdviseContext.Provider value={value}>{children}</AdviseContext.Provider>;
}

export function useAdvise(): AdviseContextValue {
  const ctx = useContext(AdviseContext);
  if (!ctx) throw new Error('useAdvise requires AdviseProvider');
  return ctx;
}

export function useAdviseOptional(): AdviseContextValue | null {
  return useContext(AdviseContext);
}
