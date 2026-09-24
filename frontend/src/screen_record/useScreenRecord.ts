/**
 * The trading screen recording's status, live: subscribes once to the Electron
 * bridge (`window.novaDesktop.screenRecord`, electron/preload.cjs). In a
 * browser there is no bridge: `desktop` is false and the screen is not
 * recorded, which the chip says.
 */
import { useEffect, useState } from 'react';
import { readScreenRecordView, type ScreenRecordView } from './screenRecordView';

export type ScreenRecordBridge = NonNullable<NonNullable<Window['novaDesktop']>['screenRecord']>;

export function useScreenRecord(bridgeProp?: ScreenRecordBridge | null) {
  // Read once: a new object each render would re-subscribe every render.
  const [bridge] = useState(() => (bridgeProp === undefined ? window.novaDesktop?.screenRecord ?? null : bridgeProp));
  const [view, setView] = useState<ScreenRecordView | null>(null);

  useEffect(() => {
    if (!bridge) return undefined;
    return bridge.subscribe((raw) => setView(readScreenRecordView(raw)));
  }, [bridge]);

  return { desktop: bridge !== null, view };
}
