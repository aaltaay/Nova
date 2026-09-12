import { useCallback, useState } from 'react';
import { useMaximizedChartPortal } from '../hooks/useMaximizedChartPortal';
import { consumeEscapeForFullscreen } from './chartFullscreen';
import { useChartFullscreen } from './useChartFullscreen';

interface Options {
  /** Trader 2x2: double-click expands inside the chart grid (parent-owned). */
  maximizeInGrid?: boolean;
  maximized?: boolean;
  onMaximizeChange?: (next: boolean) => void;
}

/**
 * Two expand paths:
 * - Quote / standalone: header ⛶ portals over the Nova desk.
 * - Trader grid: header ⛶ is browser/OS fullscreen; `maximized` is grid-only.
 */
export function useTickerChartMaximize({
  maximizeInGrid = false,
  maximized: controlledMaximized,
  onMaximizeChange,
}: Options) {
  const [localMaximized, setLocalMaximized] = useState(false);
  const isControlled = onMaximizeChange !== undefined && controlledMaximized !== undefined;
  const portalMaximized = !maximizeInGrid && (isControlled ? controlledMaximized : localMaximized);
  const gridMaximized = Boolean(maximizeInGrid && controlledMaximized);
  const { slotRef, host } = useMaximizedChartPortal(portalMaximized);
  const { isFullscreen, toggleFullscreen, exitFullscreen } = useChartFullscreen(
    host,
    maximizeInGrid,
  );

  const setMaximized = useCallback(
    (next: boolean) => {
      if (maximizeInGrid) {
        if (!next) {
          consumeEscapeForFullscreen();
          exitFullscreen();
        }
        return;
      }
      if (isControlled) onMaximizeChange(next);
      else setLocalMaximized(next);
    },
    [exitFullscreen, isControlled, maximizeInGrid, onMaximizeChange],
  );

  const toggleMaximize = useCallback(() => {
    if (maximizeInGrid) {
      toggleFullscreen();
      return;
    }
    setMaximized(!portalMaximized);
  }, [maximizeInGrid, portalMaximized, setMaximized, toggleFullscreen]);

  const headerMaximized = maximizeInGrid ? isFullscreen : portalMaximized;
  const maximized = portalMaximized || gridMaximized || isFullscreen;

  return {
    maximized,
    headerMaximized,
    isFullscreen,
    setMaximized,
    toggleMaximize,
    portalMaximized,
    slotRef,
    host,
  };
}
