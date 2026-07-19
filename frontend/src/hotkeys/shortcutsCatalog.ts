/**
 * Build the live list of bound Nova shortcuts for the Ctrl+M menu.
 */

import {
  HOTKEY_ACTION_LABELS,
  HOTKEY_ACTIONS,
  HOTKEY_DEFAULTS,
  NOVA_ACTION_KIND_LABELS,
  SHORTCUTS_MENU_TITLE,
  type HotkeyAction,
  type HotkeyBinding,
} from '../constants';
import { formatHotkeyLabel } from '../hooks/hotkeyUtils';
import { formatKeyChord } from './htkFormat';
import type { NovaActionRecord } from './novaActionTypes';
import type { HotkeyKeyChord } from './types';

export type ShortcutRebindTarget =
  | { type: 'menu' }
  | { type: 'automation'; action: HotkeyAction }
  | { type: 'nova'; id: string };

export type ShortcutCatalogRow = {
  id: string;
  chord: string;
  label: string;
  detail?: string;
  rebind?: ShortcutRebindTarget;
};

export type ShortcutCatalogSection = {
  id: string;
  title: string;
  rows: ShortcutCatalogRow[];
};

export function buildShortcutsCatalog(
  novaActions: NovaActionRecord[],
  automationBindings: Record<HotkeyAction, HotkeyBinding> = HOTKEY_DEFAULTS,
  menuBinding: HotkeyBinding = { key: 'm', ctrl: true },
): ShortcutCatalogSection[] {
  const menu: ShortcutCatalogSection = {
    id: 'menu',
    title: SHORTCUTS_MENU_TITLE,
    rows: [
      {
        id: 'menu:shortcuts_menu',
        chord: formatHotkeyLabel(menuBinding),
        label: 'Show this menu',
        detail: 'Double-click to rebind · hold to peek · twice to pin',
        rebind: { type: 'menu' },
      },
    ],
  };

  const automation: ShortcutCatalogSection = {
    id: 'automation',
    title: 'Automation (System 1)',
    rows: HOTKEY_ACTIONS.map((action: HotkeyAction) => ({
      id: `auto_${action}`,
      chord: formatHotkeyLabel(automationBindings[action]),
      label: HOTKEY_ACTION_LABELS[action],
      rebind: { type: 'automation', action },
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
        rebind: { type: 'nova', id: a.id },
      })),
  };

  return [menu, automation, nova];
}

export function catalogRowChord(
  target: ShortcutRebindTarget,
  novaActions: NovaActionRecord[],
  automation: Record<HotkeyAction, HotkeyBinding>,
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
  if (target.type === 'automation') {
    const b = automation[target.action];
    return {
      label: formatHotkeyLabel(b),
      key: b.key,
      ctrl: b.ctrl,
      shift: b.shift,
      alt: b.alt,
      meta: b.meta,
    };
  }
  const row = novaActions.find((a) => a.id === target.id);
  return row?.key ?? null;
}
