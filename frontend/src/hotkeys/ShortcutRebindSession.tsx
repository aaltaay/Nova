/**
 * TanStack HotkeyRecorder session — capture a new chord while the menu is open.
 * Bare modifiers (Alt/Ctrl/…) are accepted via a parallel keyup path because
 * TanStack ignores modifier-only keydowns.
 */

import { useEffect, useRef } from 'react';
import { useHotkeyRecorder, type Hotkey } from '@tanstack/react-hotkeys';
import {
  SHORTCUTS_MENU_CONFLICT_PREFIX,
  SHORTCUTS_MENU_REBIND_HINT,
} from '../constants';
import {
  initialBareModifierRecordState,
  reduceBareModifierRecordKeyDown,
  reduceBareModifierRecordKeyUp,
} from './bareModifierRecord';
import { findShortcutConflict } from './shortcutConflicts';
import type { ShortcutOccupiedSlot } from './shortcutConflicts';
import type { ShortcutRebindTarget } from './shortcutsCatalog';
import { tanstackHotkeyToChord } from './tanstackChord';
import type { HotkeyKeyChord } from './types';

type Props = {
  target: ShortcutRebindTarget;
  excludeId: string;
  occupied: ShortcutOccupiedSlot[];
  onApplied: (target: ShortcutRebindTarget, chord: HotkeyKeyChord) => void;
  onConflict: (message: string) => void;
  onCancel: () => void;
};

export function ShortcutRebindSession({
  target,
  excludeId,
  occupied,
  onApplied,
  onConflict,
  onCancel,
}: Props) {
  const occupiedRef = useRef(occupied);
  occupiedRef.current = occupied;
  const targetRef = useRef(target);
  targetRef.current = target;
  const startRef = useRef<() => void>(() => {});
  const onCancelRef = useRef(onCancel);
  onCancelRef.current = onCancel;
  const onAppliedRef = useRef(onApplied);
  onAppliedRef.current = onApplied;
  const onConflictRef = useRef(onConflict);
  onConflictRef.current = onConflict;
  const excludeIdRef = useRef(excludeId);
  excludeIdRef.current = excludeId;
  const doneRef = useRef(false);

  const applyChord = (chord: HotkeyKeyChord) => {
    if (doneRef.current) return;
    const hit = findShortcutConflict(
      chord,
      occupiedRef.current,
      excludeIdRef.current,
    );
    if (hit) {
      onConflictRef.current(
        `${SHORTCUTS_MENU_CONFLICT_PREFIX} “${hit.label}” (${hit.chord})`,
      );
      queueMicrotask(() => startRef.current());
      return;
    }
    doneRef.current = true;
    onAppliedRef.current(targetRef.current, chord);
  };

  const recorder = useHotkeyRecorder({
    ignoreInputs: false,
    // Escape during an active session — not React StrictMode unmount.
    onCancel: () => {
      onCancelRef.current();
    },
    onRecord: (hotkey: Hotkey) => {
      if (!hotkey) {
        queueMicrotask(() => startRef.current());
        return;
      }
      applyChord(tanstackHotkeyToChord(hotkey));
    },
  });

  startRef.current = recorder.startRecording;

  useEffect(() => {
    doneRef.current = false;
    recorder.startRecording();
    return () => {
      // stop() does NOT call onCancel — cancel() would clear the parent
      // rebindTarget in React StrictMode (mount → cleanup → remount).
      recorder.stopRecording();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- one session per mount
  }, []);

  // TanStack returns null for modifier-only keydowns — accept bare Alt/Ctrl/… on keyup.
  useEffect(() => {
    let state = initialBareModifierRecordState();
    const onKeyDown = (event: KeyboardEvent) => {
      state = reduceBareModifierRecordKeyDown(state, event);
    };
    const onKeyUp = (event: KeyboardEvent) => {
      const next = reduceBareModifierRecordKeyUp(state, event);
      state = next.state;
      if (!next.chord) return;
      event.preventDefault();
      event.stopPropagation();
      applyChord(next.chord);
    };
    window.addEventListener('keydown', onKeyDown, true);
    window.addEventListener('keyup', onKeyUp, true);
    return () => {
      window.removeEventListener('keydown', onKeyDown, true);
      window.removeEventListener('keyup', onKeyUp, true);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- one session per mount
  }, []);

  return (
    <div className="shortcuts-menu-rebind" role="status" aria-live="polite">
      <strong>{SHORTCUTS_MENU_REBIND_HINT}</strong>
      {recorder.isRecording && (
        <span className="shortcuts-menu-rebind-live"> Listening…</span>
      )}
      {recorder.recordedHotkey && (
        <span className="shortcuts-menu-rebind-preview">
          {` (${recorder.recordedHotkey})`}
        </span>
      )}
      <button
        type="button"
        className="btn-secondary shortcuts-menu-rebind-cancel"
        onClick={onCancel}
      >
        Cancel
      </button>
    </div>
  );
}
