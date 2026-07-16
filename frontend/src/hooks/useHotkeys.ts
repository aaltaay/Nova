import { useEffect, useRef } from 'react';
import type { HotkeyAction } from '../constants';
import { createHotkeyKeydownHandler, type HotkeyCallbacks } from './hotkeyUtils';

export type { HotkeyCallbacks };

export interface UseHotkeysOptions {
  enabled: boolean;
  mode: string;
  callbacks: HotkeyCallbacks;
  onBlocked?: (action: HotkeyAction, message: string) => void;
}

/** Register global keydown handlers for executor shortcuts when the panel is active. */
export function useHotkeys({ enabled, mode, callbacks, onBlocked }: UseHotkeysOptions): void {
  const callbacksRef = useRef(callbacks);
  const onBlockedRef = useRef(onBlocked);
  callbacksRef.current = callbacks;
  onBlockedRef.current = onBlocked;

  useEffect(() => {
    if (!enabled) return;

    const onKeyDown = (event: KeyboardEvent) => {
      createHotkeyKeydownHandler({
        mode,
        callbacks: callbacksRef.current,
        onBlocked: onBlockedRef.current,
      })(event);
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [enabled, mode]);
}
