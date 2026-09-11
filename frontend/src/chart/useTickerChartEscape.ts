import { useEffect } from 'react';

/** Escape disarms the drawing tool, then leaves maximize. */
export function useTickerChartEscape(
  activeTool: string | null,
  setActiveTool: (tool: string | null) => void,
  maximized: boolean,
  setMaximized: (value: boolean) => void,
): void {
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      if (activeTool) {
        setActiveTool(null);
        return;
      }
      if (maximized) setMaximized(false);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [activeTool, maximized, setActiveTool, setMaximized]);
}
