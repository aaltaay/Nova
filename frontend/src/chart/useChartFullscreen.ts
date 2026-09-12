import { useCallback, useEffect, useState } from 'react';
import {
  exitChartFullscreen,
  isChartFullscreen,
  markChartFullscreen,
  toggleChartFullscreen,
} from './chartFullscreen';

/** Sync React state to the Fullscreen API for one chart host. */
export function useChartFullscreen(host: HTMLElement | null, enabled: boolean) {
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    if (!enabled || !host) {
      setIsFullscreen(false);
      return;
    }
    const sync = () => {
      const next = isChartFullscreen(host);
      setIsFullscreen(next);
      if (next) {
        markChartFullscreen(true);
        host.setAttribute('data-chart-fullscreen', '1');
      } else {
        host.removeAttribute('data-chart-fullscreen');
        // Keep the flag through the Esc that just exited FS so grid restore waits.
        queueMicrotask(() => {
          if (!isChartFullscreen(host)) markChartFullscreen(false);
        });
      }
    };
    sync();
    document.addEventListener('fullscreenchange', sync);
    document.addEventListener('webkitfullscreenchange', sync);
    return () => {
      document.removeEventListener('fullscreenchange', sync);
      document.removeEventListener('webkitfullscreenchange', sync);
      host.removeAttribute('data-chart-fullscreen');
    };
  }, [enabled, host]);

  const toggleFullscreen = useCallback(() => {
    if (!enabled || !host) return;
    void toggleChartFullscreen(host);
  }, [enabled, host]);

  const exitFullscreen = useCallback(() => {
    if (!enabled) return;
    void exitChartFullscreen();
  }, [enabled]);

  return { isFullscreen, toggleFullscreen, exitFullscreen };
}
