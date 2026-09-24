/**
 * The desktop app's update view, live: subscribes once to the Electron bridge
 * (`window.novaDesktop.updates`, electron/preload.cjs) and sends the operator's
 * answers back. In a browser there is no bridge and the view stays null.
 */
import { useCallback, useEffect, useState } from 'react';
import { readUpdateView, type UpdateAction, type UpdateView } from './updateView';

export type DesktopUpdatesBridge = NonNullable<NonNullable<Window['novaDesktop']>['updates']>;

export function useDesktopUpdate(bridgeProp?: DesktopUpdatesBridge | null) {
  // Read once: a new object each render would re-subscribe every render.
  const [bridge] = useState(() => (bridgeProp === undefined ? window.novaDesktop?.updates ?? null : bridgeProp));
  const [view, setView] = useState<UpdateView | null>(null);

  useEffect(() => {
    if (!bridge) return undefined;
    return bridge.subscribe((raw) => setView(readUpdateView(raw)));
  }, [bridge]);

  const act = useCallback(
    (action: UpdateAction, url?: string) => {
      if (!bridge) return;
      bridge
        .act(url ? { action, url } : { action })
        .then((reply) => {
          if (!reply?.ok) console.warn('[nova] update action refused', action, reply?.error);
        })
        .catch((err: unknown) => console.warn('[nova] update action failed', action, err));
    },
    [bridge],
  );

  return { view, act };
}
