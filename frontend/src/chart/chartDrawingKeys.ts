/** Keyboard rules for removing a selected chart drawing (ADR 005). */

import { isEditableTarget } from '../hooks/hotkeyUtils';

const DRAWING_DELETE_KEYS = new Set(['Delete', 'Backspace']);

export function shouldDeleteSelectedDrawing(
  event: KeyboardEvent,
  hasSelection: boolean,
): boolean {
  if (!hasSelection || event.repeat) return false;
  if (event.ctrlKey || event.altKey || event.metaKey || event.shiftKey) return false;
  if (!DRAWING_DELETE_KEYS.has(event.key) && event.code !== 'Delete') return false;
  if (isEditableTarget(event.target)) return false;
  return true;
}

export function deleteSelectedDrawingOnKey(
  manager: {
    getSelectedDrawing: () => { id: string } | null;
    removeDrawing: (id: string) => void;
  },
  event: KeyboardEvent,
): boolean {
  const selected = manager.getSelectedDrawing();
  if (!selected || !shouldDeleteSelectedDrawing(event, true)) return false;
  event.preventDefault();
  manager.removeDrawing(selected.id);
  return true;
}
