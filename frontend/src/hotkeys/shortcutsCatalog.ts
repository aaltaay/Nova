/**
 * Build the live list of bound Nova shortcuts for the Ctrl+M menu.
 */

import {
  HOTKEY_ACTION_LABELS,
  HOTKEY_ACTIONS,
  HOTKEY_DEFAULTS,
  NOVA_ACTION_KIND_LABELS,
  SHORTCUTS_MENU_BINDING,
  SHORTCUTS_MENU_TITLE,
  type HotkeyAction,
} from '../constants';
import { formatHotkeyLabel } from '../hooks/hotkeyUtils';
import { formatKeyChord } from './htkFormat';
import type { NovaActionRecord } from './novaActionTypes';

export type ShortcutCatalogRow = {
  id: string;
  chord: string;
  label: string;
  detail?: string;
};

export type ShortcutCatalogSection = {
  id: string;
  title: string;
  rows: ShortcutCatalogRow[];
};

export function buildShortcutsCatalog(
  novaActions: NovaActionRecord[],
): ShortcutCatalogSection[] {
  const menu: ShortcutCatalogSection = {
    id: 'menu',
    title: SHORTCUTS_MENU_TITLE,
    rows: [
      {
        id: 'shortcuts_menu',
        chord: formatHotkeyLabel(SHORTCUTS_MENU_BINDING),
        label: 'Show this menu',
        detail: 'Hold to peek · Ctrl+M twice to pin',
      },
    ],
  };

  const automation: ShortcutCatalogSection = {
    id: 'automation',
    title: 'Automation (System 1)',
    rows: HOTKEY_ACTIONS.map((action: HotkeyAction) => ({
      id: `auto_${action}`,
      chord: formatHotkeyLabel(HOTKEY_DEFAULTS[action]),
      label: HOTKEY_ACTION_LABELS[action],
    })),
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
      })),
  };

  return [menu, automation, nova];
}
