/**
 * TanStack HotkeyRecorder session — capture a new chord while the menu is open.
 */

import { useEffect, useRef } from 'react';
import { useHotkeyRecorder, type Hotkey } from '@tanstack/react-hotkeys';
import {
  SHORTCUTS_MENU_CONFLICT_PREFIX,
  SHORTCUTS_MENU_REBIND_HINT,
} from '../constants';
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

  const recorder = useHotkeyRecorder({
    ignoreInputs: false,
    onCancel,
    onRecord: (hotkey: Hotkey) => {
      const chord = tanstackHotkeyToChord(hotkey);
      const hit = findShortcutConflict(chord, occupiedRef.current, excludeId);
      if (hit) {
        onConflict(
          `${SHORTCUTS_MENU_CONFLICT_PREFIX} “${hit.label}” (${hit.chord})`,
        );
        queueMicrotask(() => startRef.current());
        return;
      }
      onApplied(targetRef.current, chord);
    },
  });

  startRef.current = recorder.startRecording;

  useEffect(() => {
    recorder.startRecording();
    return () => {
      recorder.cancelRecording();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- one session per mount
  }, []);

  return (
    <p className="shortcuts-menu-rebind" role="status">
      {SHORTCUTS_MENU_REBIND_HINT}
      {recorder.recordedHotkey && (
        <span className="shortcuts-menu-rebind-preview">
          {` (${recorder.recordedHotkey})`}
        </span>
      )}
    </p>
  );
}
