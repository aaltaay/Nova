/**
 * Single shell-level hotkey dispatcher (Phase G3).
 * Merges Automation six + Nova Actions — one keydown listener.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import type { HotkeyAction } from '../constants';
import {
  createHotkeyKeydownHandler,
  type HotkeyCallbacks,
} from '../hooks/hotkeyUtils';
import { loadProfile } from './hotkeyStorage';
import type { NovaActionRecord, NovaActionResult } from './novaActionTypes';
import { runNovaAction, type NovaActionRuntime } from './runNovaAction';
import { useTopOfBook } from './TopOfBookContext';

interface AutomationRegistration {
  enabled: boolean;
  mode: string;
  callbacks: HotkeyCallbacks;
  onBlocked?: (action: HotkeyAction, message: string) => void;
}

export interface HotkeyDispatchContextValue {
  registerAutomation: (reg: AutomationRegistration | null) => void;
  novaActions: NovaActionRecord[];
  reloadNovaActions: () => void;
  lastResult: NovaActionResult | null;
  setRuntime: (partial: Partial<NovaActionRuntime>) => void;
  runAction: (action: NovaActionRecord) => Promise<NovaActionResult>;
}

const HotkeyDispatchContext = createContext<HotkeyDispatchContextValue | null>(null);

export function HotkeyDispatchProvider({ children }: { children: ReactNode }) {
  const [automationEnabled, setAutomationEnabled] = useState(false);
  const [automationMode, setAutomationMode] = useState('signal');
  const automationCallbacksRef = useRef<HotkeyCallbacks>({});
  const automationBlockedRef = useRef<
    ((action: HotkeyAction, message: string) => void) | undefined
  >(undefined);

  const [novaActions, setNovaActions] = useState<NovaActionRecord[]>(
    () => loadProfile().novaActions,
  );
  const [lastResult, setLastResult] = useState<NovaActionResult | null>(null);
  const runtimeRef = useRef<NovaActionRuntime>({
    symbol: null,
    connected: false,
    position: null,
    topOfBook: null,
  });
  const { topOfBook } = useTopOfBook();

  useEffect(() => {
    runtimeRef.current = { ...runtimeRef.current, topOfBook };
  }, [topOfBook]);

  const registerAutomation = useCallback((reg: AutomationRegistration | null) => {
    if (!reg || !reg.enabled) {
      setAutomationEnabled(false);
      automationCallbacksRef.current = {};
      automationBlockedRef.current = undefined;
      return;
    }
    setAutomationEnabled(true);
    setAutomationMode(reg.mode);
    automationCallbacksRef.current = reg.callbacks;
    automationBlockedRef.current = reg.onBlocked;
  }, []);

  const reloadNovaActions = useCallback(() => {
    setNovaActions(loadProfile().novaActions);
  }, []);

  const setRuntime = useCallback((partial: Partial<NovaActionRuntime>) => {
    runtimeRef.current = { ...runtimeRef.current, ...partial };
  }, []);

  const runAction = useCallback(async (action: NovaActionRecord) => {
    const result = await runNovaAction(action, runtimeRef.current);
    setLastResult(result);
    return result;
  }, []);

  const novaActionsRef = useRef(novaActions);
  novaActionsRef.current = novaActions;

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      createHotkeyKeydownHandler({
        mode: automationEnabled ? automationMode : 'signal',
        callbacks: automationEnabled ? automationCallbacksRef.current : {},
        onBlocked: automationBlockedRef.current,
        novaActions: novaActionsRef.current,
        onNovaAction: (action) => {
          void runAction(action);
        },
      })(event);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [automationEnabled, automationMode, runAction]);

  const value = useMemo(
    () => ({
      registerAutomation,
      novaActions,
      reloadNovaActions,
      lastResult,
      setRuntime,
      runAction,
    }),
    [
      registerAutomation,
      novaActions,
      reloadNovaActions,
      lastResult,
      setRuntime,
      runAction,
    ],
  );

  return (
    <HotkeyDispatchContext.Provider value={value}>
      {children}
    </HotkeyDispatchContext.Provider>
  );
}

export function useHotkeyDispatch(): HotkeyDispatchContextValue {
  const ctx = useContext(HotkeyDispatchContext);
  if (!ctx) {
    throw new Error('useHotkeyDispatch requires HotkeyDispatchProvider');
  }
  return ctx;
}

/** Safe variant for components that may render outside the provider (tests). */
export function useHotkeyDispatchOptional(): HotkeyDispatchContextValue | null {
  return useContext(HotkeyDispatchContext);
}
