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
});
