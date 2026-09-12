import { useCallback, useState } from 'react';
import { useMaximizedChartPortal } from '../hooks/useMaximizedChartPortal';

interface Options {
  /** Trader 2x2: expand inside the chart grid, do not portal over quote/trade rails. */
  maximizeInGrid?: boolean;
  maximized?: boolean;
  onMaximizeChange?: (next: boolean) => void;
}

/** Local or controlled maximize. Grid scope never reparents to document.body. */
export function useTickerChartMaximize({
  maximizeInGrid = false,
  maximized: controlledMaximized,
  onMaximizeChange,
}: Options) {
  const [localMaximized, setLocalMaximized] = useState(false);
  const isControlled = onMaximizeChange !== undefined && controlledMaximized !== undefined;
  const maximized = isControlled ? controlledMaximized : localMaximized;

  const setMaximized = useCallback(
    (next: boolean) => {
      if (isControlled) onMaximizeChange(next);
      else setLocalMaximized(next);
    },
    [isControlled, onMaximizeChange],
  );

  const toggleMaximize = useCallback(() => {
    setMaximized(!maximized);
  }, [maximized, setMaximized]);

  const portalMaximized = !maximizeInGrid && maximized;
  const { slotRef, host } = useMaximizedChartPortal(portalMaximized);

  return { maximized, setMaximized, toggleMaximize, portalMaximized, slotRef, host };
}
