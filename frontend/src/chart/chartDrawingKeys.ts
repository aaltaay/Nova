/** Keyboard rules for removing a selected chart drawing (ADR 005). */

import { isEditableTarget } from '../hooks/hotkeyUtils';
import { CHART_LINE_TOOLS } from './chartDrawingConfig';

const DRAWING_DELETE_KEYS = new Set(['Delete', 'Backspace']);
const DRAWING_HOTKEYS = new Map(CHART_LINE_TOOLS.map((tool) => [tool.key, tool.id]));
let focusedChartOwner: symbol | null = null;

export function claimChartDrawingHotkeyFocus(owner: symbol): void {
  focusedChartOwner = owner;
}

export function releaseChartDrawingHotkeyFocus(owner: symbol): void {
  if (focusedChartOwner === owner) focusedChartOwner = null;
}

export function ownsChartDrawingHotkeyFocus(owner: symbol): boolean {
  return focusedChartOwner === owner;
}

export function resolveChartDrawingHotkey(event: KeyboardEvent): string | null {
  if (event.repeat || !event.altKey || event.ctrlKey || event.metaKey) return null;
  if (isEditableTarget(event.target)) return null;
  return DRAWING_HOTKEYS.get(event.key.toLowerCase()) ?? null;
}

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
