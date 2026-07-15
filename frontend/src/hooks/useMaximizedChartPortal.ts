/**
 * Keeps the chart DOM under a stable host element that moves between an
 * in-flow slot and document.body when maximized. Moving the host (not
 * remounting via createPortal target swap) preserves the lightweight-charts
 * instance so candles do not blank and refetch.
 */
import { useLayoutEffect, useRef } from 'react';

export function useMaximizedChartPortal(maximized: boolean) {
  const slotRef = useRef<HTMLDivElement>(null);
  const hostRef = useRef<HTMLDivElement | null>(null);

  if (hostRef.current === null) {
    hostRef.current = document.createElement('div');
    hostRef.current.className = 'chart-portal-host';
  }
  const host = hostRef.current;

  // Mount host into the in-flow slot; tear down only when the chart unmounts.
  useLayoutEffect(() => {
    const slot = slotRef.current;
    if (!slot) return;
    slot.appendChild(host);
    return () => {
      host.remove();
      document.body.classList.remove('chart-maximized-open');
    };
  }, [host]);

  // Reparent the same host to body while maximized so position:fixed is
  // viewport-relative (side-panel container-type would otherwise trap it).
  useLayoutEffect(() => {
    const slot = slotRef.current;
    if (maximized) {
      document.body.appendChild(host);
      host.classList.add('chart-portal-host--maximized');
      document.body.classList.add('chart-maximized-open');
    } else if (slot) {
      slot.appendChild(host);
      host.classList.remove('chart-portal-host--maximized');
      document.body.classList.remove('chart-maximized-open');
    }
  }, [maximized, host]);

  return { slotRef, host };
}
