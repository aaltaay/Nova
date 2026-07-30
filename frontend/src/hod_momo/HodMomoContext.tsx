/**
 * Shared HOD Momo context — live provider and sample fixture provider both use this.
 */
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { collapseAlertsBySymbol } from './collapseAlertsBySymbol';
import {
  clampDockHeightPx,
  readDockCollapsed,
  readDockHeightPx,
  writeDockCollapsed,
  writeDockHeightPx,
} from './hodMomoDockPersist';
import { partitionScannerAlerts } from './scannerPartition';
import type { useHodMomoConfig } from './useHodMomoConfig';
import type { useHodMomoStream } from './useHodMomoStream';

export type HodDockMode = 'hod_momo' | 'running_up';

type HodStream = ReturnType<typeof useHodMomoStream>;
type HodConfig = ReturnType<typeof useHodMomoConfig>;

export type HodMomoContextValue = {
  stream: HodStream;
  config: HodConfig;
  hodCount: number;
  runningUpCount: number;
  dockMode: HodDockMode;
  setDockMode: (mode: HodDockMode) => void;
  collapsed: boolean;
  setCollapsed: (collapsed: boolean) => void;
  toggleCollapsed: () => void;
  heightPx: number;
  setHeightPx: (px: number) => void;
  focusDock: (mode: HodDockMode) => void;
  showHodSettings: boolean;
  setShowHodSettings: (open: boolean) => void;
  toggleHodSettings: () => void;
};

const HodMomoContext = createContext<HodMomoContextValue | null>(null);

export function useHodMomoDockState(stream: HodStream) {
  const [dockMode, setDockMode] = useState<HodDockMode>('hod_momo');
  const [collapsed, setCollapsedState] = useState(readDockCollapsed);
  const [heightPx, setHeightState] = useState(readDockHeightPx);
  const [showHodSettings, setShowHodSettings] = useState(false);

  const setCollapsed = useCallback((next: boolean) => {
    setCollapsedState(next);
    writeDockCollapsed(next);
  }, []);

  const toggleCollapsed = useCallback(() => {
    setCollapsedState((prev) => {
      const next = !prev;
      writeDockCollapsed(next);
      return next;
    });
  }, []);

  const setHeightPx = useCallback((px: number) => {
    const next = clampDockHeightPx(px);
    setHeightState(next);
    writeDockHeightPx(next);
  }, []);

  const focusDock = useCallback((mode: HodDockMode) => {
    setDockMode(mode);
    setCollapsedState(false);
    writeDockCollapsed(false);
  }, []);

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
      collapsed,
      setCollapsed,
      toggleCollapsed,
      heightPx,
      setHeightPx,
      focusDock,
      showHodSettings,
      setShowHodSettings,
      toggleHodSettings,
      hodCount,
      runningUpCount,
    }),
    [
      dockMode,
      collapsed,
      setCollapsed,
      toggleCollapsed,
      heightPx,
      setHeightPx,
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
