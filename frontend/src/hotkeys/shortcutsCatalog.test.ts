import { describe, expect, it } from 'vitest';
import { buildShortcutsCatalog } from './shortcutsCatalog';
import type { NovaActionRecord } from './novaActionTypes';

describe('buildShortcutsCatalog', () => {
  it('includes the menu and enabled nova actions with rebind targets', () => {
    const actions: NovaActionRecord[] = [
      {
        id: 'a1',
        name: 'Cancel symb',
        kind: 'cancel_symbol',
        key: { label: 'Ctrl+PageUp', key: 'PageUp', ctrl: true },
        params: {},
        enabled: true,
        showButton: false,
      },
    ];
    const sections = buildShortcutsCatalog(actions);
    expect(sections.map((s) => s.id)).toEqual(['menu', 'nova_actions']);
    expect(sections[0].rows[0].rebind).toEqual({ type: 'menu' });
    expect(sections[1].rows[0].rebind).toEqual({ type: 'nova', id: 'a1' });
    expect(sections[1].rows[0].canEditAction).toBe(true);
    expect(sections[1].rows[0].canDelete).toBe(true);
    expect(sections[0].rows[0].canEditAction).toBeUndefined();
    expect(sections[0].rows[0].canDelete).toBeUndefined();
  });

  it('lists Ctrl+F find on the page, unless a Nova Action owns Ctrl+F', () => {
    const find = buildShortcutsCatalog([])[0].rows.find((r) => r.id === 'menu:find_on_page');
    expect(find).toMatchObject({ chord: 'Ctrl+F', label: 'Find on this page' });
    expect(find?.rebind).toBeUndefined();
    const owner: NovaActionRecord = {
      id: 'f1',
      name: 'Flatten',
      kind: 'exit_pos',
      key: { label: 'Ctrl+F', key: 'F', ctrl: true },
      params: {},
      enabled: true,
      showButton: false,
    };
    const rows = buildShortcutsCatalog([owner])[0].rows;
    expect(rows.some((r) => r.id === 'menu:find_on_page')).toBe(false);
    const idle = buildShortcutsCatalog([{ ...owner, enabled: false }])[0].rows;
    expect(idle.some((r) => r.id === 'menu:find_on_page')).toBe(true);
  });
});
