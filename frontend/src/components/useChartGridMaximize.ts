import { useEffect, useState } from 'react';
import { shouldRestoreGridOnEscape } from '../chart/chartFullscreen';
import { shouldToggleChartPaneMaximize } from '../chart/chartPaneMaximize';

/** Session-only: which Trader grid pane fills the chart region. */
export function useChartGridMaximize(
  panelIds: readonly string[],
  activeTool: string | null,
  setActiveTool: (tool: string | null) => void,
) {
  const [maximizedPaneId, setMaximizedPaneId] = useState<string | null>(null);

  useEffect(() => {
    if (maximizedPaneId && !panelIds.includes(maximizedPaneId)) {
      setMaximizedPaneId(null);
    }
  }, [panelIds, maximizedPaneId]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      if (activeTool) {
        setActiveTool(null);
        return;
      }
      if (!shouldRestoreGridOnEscape(event, activeTool)) return;
      if (maximizedPaneId) setMaximizedPaneId(null);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [activeTool, maximizedPaneId, setActiveTool]);

  const setPaneMaximized = (paneId: string, next: boolean) => {
    setMaximizedPaneId(next ? paneId : null);
  };

  const onCellDoubleClick = (paneId: string, event: { target: EventTarget | null }) => {
    if (!shouldToggleChartPaneMaximize(event, activeTool)) return;
    setMaximizedPaneId((current) => (current === paneId ? null : paneId));
  };

  const restore = () => setMaximizedPaneId(null);

  return { maximizedPaneId, setPaneMaximized, onCellDoubleClick, restore };
}
