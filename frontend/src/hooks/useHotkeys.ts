import { useEffect, useRef } from 'react';
import type { HotkeyAction } from '../constants';
import { useHotkeyDispatchOptional } from '../hotkeys/HotkeyDispatchContext';
import { createHotkeyKeydownHandler, type HotkeyCallbacks } from './hotkeyUtils';

export type { HotkeyCallbacks };

export interface UseHotkeysOptions {
  enabled: boolean;
  mode: string;
  callbacks: HotkeyCallbacks;
  onBlocked?: (action: HotkeyAction, message: string) => void;
}

/**
 * Registers Automation six callbacks with the shell-level dispatcher when present.
 * Falls back to a local window listener (tests / no provider).
 */
export function useHotkeys({ enabled, mode, callbacks, onBlocked }: UseHotkeysOptions): void {
  const dispatch = useHotkeyDispatchOptional();
  const callbacksRef = useRef(callbacks);
  const onBlockedRef = useRef(onBlocked);
  callbacksRef.current = callbacks;
  onBlockedRef.current = onBlocked;

  useEffect(() => {
    if (dispatch) {
      if (!enabled) {
        dispatch.registerAutomation(null);
        return () => dispatch.registerAutomation(null);
      }
      dispatch.registerAutomation({
        enabled,
        mode,
        callbacks,
        onBlocked,
      });
      return () => dispatch.registerAutomation(null);
    }

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
  }, [dispatch, enabled, mode, callbacks, onBlocked]);
}
