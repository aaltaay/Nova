/**
 * Shared HOD Momo context — live provider and sample fixture provider both use this.
 * Strip layout (rows + folded) is one versioned localStorage blob owned by
 * hodMomoStripPersist.ts.
 */
import {
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { hmrStableContext } from '../utils/hmrStableContext';
import { collapseAlertsBySymbol } from './collapseAlertsBySymbol';
import {
  clampStripRows,
  readStripLayout,
  writeStripLayout,
  type HodMomoStripLayout,
} from './hodMomoStripPersist';
import { type HodDockMode } from './scannerDockModes';
import { partitionScannerAlerts } from './scannerPartition';
import type { useHodMomoConfig } from './useHodMomoConfig';
import type { useHodMomoStream } from './useHodMomoStream';
import type { HodMomoReplayState } from './useHodMomoReplay';

export type { HodDockMode } from './scannerDockModes';

type HodStream = ReturnType<typeof useHodMomoStream>;
type HodConfig = ReturnType<typeof useHodMomoConfig>;

export type HodMomoContextValue = {
  stream: HodStream;
  config: HodConfig;
  hodCount: number;
  runningUpCount: number;
  dockMode: HodDockMode;
  setDockMode: (mode: HodDockMode) => void;
  /** Folded to its header line. */
  collapsed: boolean;
  setCollapsed: (collapsed: boolean) => void;
  toggleCollapsed: () => void;
  /** Whole alert rows the unfolded strip shows (persisted). */
  rows: number;
  setRows: (rows: number) => void;
  focusDock: (mode: HodDockMode) => void;
  showHodSettings: boolean;
  setShowHodSettings: (open: boolean) => void;
  toggleHodSettings: () => void;
  /**
   * Sim off the live edge (ADR 022): `stream.alerts` are the day's history up
   * to the playhead, not the live socket. Null / absent on Live and Paper.
   */
  replay?: HodMomoReplayState | null;
};

const HodMomoContext = hmrStableContext<HodMomoContextValue>(import.meta.hot, 'HodMomoContext');

export function useHodMomoDockState(stream: HodStream) {
  const [dockMode, setDockMode] = useState<HodDockMode>('hod_momo');
  const [layout, setLayout] = useState<HodMomoStripLayout>(readStripLayout);
  const [showHodSettings, setShowHodSettings] = useState(false);

  const updateLayout = useCallback((patch: (prev: HodMomoStripLayout) => HodMomoStripLayout) => {
    setLayout((prev) => {
      const next = patch(prev);
      if (next.rows === prev.rows && next.folded === prev.folded) return prev;
      writeStripLayout(next);
      return next;
    });
  }, []);

  const setCollapsed = useCallback((next: boolean) => {
    updateLayout((prev) => ({ ...prev, folded: next }));
  }, [updateLayout]);

  const toggleCollapsed = useCallback(() => {
    updateLayout((prev) => ({ ...prev, folded: !prev.folded }));
  }, [updateLayout]);

  const setRows = useCallback((rows: number) => {
    updateLayout((prev) => ({ ...prev, rows: clampStripRows(rows) }));
  }, [updateLayout]);

  const focusDock = useCallback((mode: HodDockMode) => {
    setDockMode(mode);
    updateLayout((prev) => ({ ...prev, folded: false }));
  }, [updateLayout]);

  const toggleHodSettings = useCallback(() => {
    setShowHodSettings((s) => !s);
  }, []);

  const { hodMomentum, runningUp } = useMemo(
    () => partitionScannerAlerts(stream.alerts),
    [stream.alerts],
  );
  const hodCount = useMemo(
    () => collapseAlertsBySymbol(hodMomentum).length,
    [hodMomentum],
  );
  const runningUpCount = useMemo(
    () => collapseAlertsBySymbol(runningUp).length,
    [runningUp],
  );

  return useMemo(
    () => ({
      dockMode,
      setDockMode,
      collapsed: layout.folded,
      setCollapsed,
      toggleCollapsed,
      rows: layout.rows,
      setRows,
      focusDock,
      showHodSettings,
      setShowHodSettings,
      toggleHodSettings,
      hodCount,
      runningUpCount,
    }),
    [
      dockMode,
      layout.folded,
      layout.rows,
      setCollapsed,
      toggleCollapsed,
      setRows,
      focusDock,
      showHodSettings,
      toggleHodSettings,
      hodCount,
      runningUpCount,
    ],
  );
}

export function HodMomoContextProvider({
  value,
  children,
}: {
  value: HodMomoContextValue;
  children: ReactNode;
}) {
  return (
    <HodMomoContext.Provider value={value}>{children}</HodMomoContext.Provider>
  );
}

export function useHodMomo(): HodMomoContextValue {
  const ctx = useContext(HodMomoContext);
  if (!ctx) {
    throw new Error('useHodMomo must be used within HodMomoProvider');
  }
  return ctx;
}

export function useHodMomoOptional(): HodMomoContextValue | null {
  return useContext(HodMomoContext);
}
