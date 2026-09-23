/**
 * Build the live list of bound Nova shortcuts for the hold-Ctrl+Alt menu.
 */

import {
  NOVA_ACTION_KIND_LABELS,
  SHORTCUTS_MENU_BINDING,
  SHORTCUTS_MENU_TITLE,
  type HotkeyBinding,
} from '../constants';
import { formatHotkeyLabel } from '../hooks/hotkeyUtils';
import { formatKeyChord } from './htkFormat';
import type { NovaActionRecord } from './novaActionTypes';
import type { HotkeyKeyChord } from './types';

export type ShortcutRebindTarget =
  | { type: 'menu' }
  | { type: 'nova'; id: string };

export type ShortcutCatalogRow = {
  id: string;
  chord: string;
  label: string;
  detail?: string;
  rebind?: ShortcutRebindTarget;
  /** Open the Nova Action editor (System 2 rows only). */
  canEditAction?: boolean;
  /** Two-step delete (System 2 rows only). */
  canDelete?: boolean;
};

export type ShortcutCatalogSection = {
  id: string;
  title: string;
  rows: ShortcutCatalogRow[];
};

export function buildShortcutsCatalog(
  novaActions: NovaActionRecord[],
  menuBinding: HotkeyBinding = SHORTCUTS_MENU_BINDING,
): ShortcutCatalogSection[] {
  const menu: ShortcutCatalogSection = {
    id: 'menu',
    title: SHORTCUTS_MENU_TITLE,
    rows: [
      {
        id: 'menu:shortcuts_menu',
        chord: formatHotkeyLabel(menuBinding),
        label: 'Show this menu',
        detail: 'Hold to peek · release to close · twice to pin · double-click to rebind',
        rebind: { type: 'menu' },
      },
    ],
  };

  const enabled = novaActions.filter((a) => a.enabled && a.key.key);
  const nova: ShortcutCatalogSection = {
    id: 'nova_actions',
    title: 'Nova Actions (System 2)',
    rows: enabled.length === 0
      ? [{
        id: 'nova_none',
        chord: '—',
        label: 'No enabled Nova Actions',
        detail: 'Enable them in Settings → Hotkeys',
      }]
      : enabled.map((a) => ({
        id: a.id,
        chord: formatKeyChord(a.key),
        label: a.name || NOVA_ACTION_KIND_LABELS[a.kind],
        detail: NOVA_ACTION_KIND_LABELS[a.kind],
        rebind: { type: 'nova', id: a.id },
        canEditAction: true,
        canDelete: true,
      })),
  };

  return [menu, nova];
}

export function catalogRowChord(
  target: ShortcutRebindTarget,
  novaActions: NovaActionRecord[],
  menu: HotkeyBinding,
): HotkeyKeyChord | null {
  if (target.type === 'menu') {
    return {
      label: formatHotkeyLabel(menu),
      key: menu.key,
      ctrl: menu.ctrl,
      shift: menu.shift,
      alt: menu.alt,
      meta: menu.meta,
    };
  }
  const row = novaActions.find((a) => a.id === target.id);
  return row?.key ?? null;
}
