import type { ReactNode, RefObject } from 'react';
import { createPortal } from 'react-dom';

interface Props {
  slotRef: RefObject<HTMLDivElement | null>;
  host: HTMLElement;
  portalMaximized: boolean;
  chartHeight: number;
  children: ReactNode;
}

/** Stable portal host so lightweight-charts is not remounted on maximize. */
export function ChartPortalFrame({
  slotRef,
  host,
  portalMaximized,
  chartHeight,
  children,
}: Props) {
  return (
    <div
      ref={slotRef}
      className={`chart-portal-slot${portalMaximized ? ' chart-portal-slot--maximized' : ''}`}
      style={portalMaximized ? { minHeight: chartHeight } : undefined}
    >
      {createPortal(children, host)}
    </div>
  );
}
