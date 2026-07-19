/**
 * Single shell-level hotkey dispatcher (Phase G3).
 * Automation + Nova Actions + shortcuts menu / rebind — one keydown listener.
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
import {
  collectOccupiedSlots,
  getEffectiveAutomationBindings,
  getEffectiveMenuBinding,
} from './effectiveBindings';
import { loadProfile, saveProfile } from './hotkeyStorage';
import type { NovaActionRecord, NovaActionResult } from './novaActionTypes';
import { runNovaAction, type NovaActionRuntime } from './runNovaAction';
import {
  buildShortcutsCatalog,
  type ShortcutRebindTarget,
} from './shortcutsCatalog';
import {
  initialShortcutsMenuState,
  reduceShortcutsMenuKeyDown,
  reduceShortcutsMenuKeyUp,
  type ShortcutsMenuState,
} from './shortcutsMenuState';
import { ShortcutsMenuOverlay } from './ShortcutsMenuOverlay';
import { useTopOfBook } from './TopOfBookContext';
import type { HotkeyKeyChord, HotkeyProfile } from './types';

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

function readProfile(): HotkeyProfile {
  return loadProfile();
}

export function HotkeyDispatchProvider({ children }: { children: ReactNode }) {
  const [automationEnabled, setAutomationEnabled] = useState(false);
  const [automationMode, setAutomationMode] = useState('signal');
  const automationCallbacksRef = useRef<HotkeyCallbacks>({});
  const automationBlockedRef = useRef<
    ((action: HotkeyAction, message: string) => void) | undefined
  >(undefined);

  const [profile, setProfile] = useState<HotkeyProfile>(() => readProfile());
  const [lastResult, setLastResult] = useState<NovaActionResult | null>(null);
  const [menuState, setMenuState] = useState<ShortcutsMenuState>(
    initialShortcutsMenuState,
  );
  const menuStateRef = useRef(menuState);
  menuStateRef.current = menuState;

  const [rebindTarget, setRebindTarget] = useState<ShortcutRebindTarget | null>(null);
  const [rebindExcludeId, setRebindExcludeId] = useState<string | null>(null);
  const [rebindConflict, setRebindConflict] = useState<string | null>(null);
  const rebindActiveRef = useRef(false);
  rebindActiveRef.current = rebindTarget != null;

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

  const automationBindings = useMemo(
    () => getEffectiveAutomationBindings(profile),
    [profile],
  );
  const menuBinding = useMemo(
    () => getEffectiveMenuBinding(profile),
    [profile],
  );
  const automationBindingsRef = useRef(automationBindings);
  automationBindingsRef.current = automationBindings;
  const menuBindingRef = useRef(menuBinding);
  menuBindingRef.current = menuBinding;

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
    setProfile(readProfile());
  }, []);

  const setRuntime = useCallback((partial: Partial<NovaActionRuntime>) => {
    runtimeRef.current = { ...runtimeRef.current, ...partial };
  }, []);

  const runAction = useCallback(async (action: NovaActionRecord) => {
    const result = await runNovaAction(action, runtimeRef.current);
    setLastResult(result);
    return result;
  }, []);

  const closePinnedMenu = useCallback(() => {
    setRebindTarget(null);
    setRebindExcludeId(null);
    setRebindConflict(null);
    setMenuState(initialShortcutsMenuState());
  }, []);

  const novaActionsRef = useRef(profile.novaActions);
  novaActionsRef.current = profile.novaActions;

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (rebindActiveRef.current) {
        // TanStack recorder owns the keyboard while rebinding.
        return;
      }

      const menuNext = reduceShortcutsMenuKeyDown(
        menuStateRef.current,
        event,
        performance.now(),
        undefined,
        menuBindingRef.current,
      );
      if (menuNext.consumed) {
        event.preventDefault();
        menuStateRef.current = menuNext.state;
        setMenuState(menuNext.state);
        return;
      }

      createHotkeyKeydownHandler({
        mode: automationEnabled ? automationMode : 'signal',
        callbacks: automationEnabled ? automationCallbacksRef.current : {},
        onBlocked: automationBlockedRef.current,
        novaActions: novaActionsRef.current,
        automationBindings: automationBindingsRef.current,
        onNovaAction: (action) => {
          void runAction(action);
        },
      })(event);
    };

    const onKeyUp = (event: KeyboardEvent) => {
      if (rebindActiveRef.current) return;
      const next = reduceShortcutsMenuKeyUp(
        menuStateRef.current,
        event,
        menuBindingRef.current,
      );
      if (next.mode !== menuStateRef.current.mode) {
        menuStateRef.current = next;
        setMenuState(next);
      }
    };

    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('keyup', onKeyUp);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('keyup', onKeyUp);
    };
  }, [automationEnabled, automationMode, runAction]);

  const catalog = useMemo(
    () => buildShortcutsCatalog(profile.novaActions, automationBindings, menuBinding),
    [profile.novaActions, automationBindings, menuBinding],
  );

  const occupied = useMemo(
    () => collectOccupiedSlots(automationBindings, profile.novaActions, menuBinding),
    [automationBindings, profile.novaActions, menuBinding],
  );

  const onStartRebind = useCallback((target: ShortcutRebindTarget, excludeId: string) => {
    setMenuState((s) => (s.mode === 'closed' ? s : { ...s, mode: 'pinned' }));
    setRebindConflict(null);
    setRebindTarget(target);
    setRebindExcludeId(excludeId);
  }, []);

  const onCancelRebind = useCallback(() => {
    setRebindTarget(null);
    setRebindExcludeId(null);
    setRebindConflict(null);
  }, []);

  const onApplyRebind = useCallback((target: ShortcutRebindTarget, chord: HotkeyKeyChord) => {
    setProfile((prev) => {
      let next: HotkeyProfile = { ...prev };
      if (target.type === 'menu') {
        next = { ...prev, shortcutsMenuKey: chord };
      } else if (target.type === 'automation') {
        next = {
          ...prev,
          automationBindings: {
            ...prev.automationBindings,
            [target.action]: chord,
          },
        };
      } else {
        next = {
          ...prev,
          novaActions: prev.novaActions.map((a) =>
            a.id === target.id ? { ...a, key: chord } : a,
          ),
        };
      }
      saveProfile(next);
      return next;
    });
    setRebindTarget(null);
    setRebindExcludeId(null);
    setRebindConflict(null);
  }, []);

  const value = useMemo(
    () => ({
      registerAutomation,
      novaActions: profile.novaActions,
      reloadNovaActions,
      lastResult,
      setRuntime,
      runAction,
    }),
    [
      registerAutomation,
      profile.novaActions,
      reloadNovaActions,
      lastResult,
      setRuntime,
      runAction,
    ],
  );

  return (
    <HotkeyDispatchContext.Provider value={value}>
      {children}
      <ShortcutsMenuOverlay
        mode={menuState.mode}
        sections={catalog}
        occupied={occupied}
        rebindTarget={rebindTarget}
        rebindExcludeId={rebindExcludeId}
        rebindConflict={rebindConflict}
        onClosePinned={closePinnedMenu}
        onStartRebind={onStartRebind}
        onApplyRebind={onApplyRebind}
        onRebindConflict={setRebindConflict}
        onCancelRebind={onCancelRebind}
      />
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
