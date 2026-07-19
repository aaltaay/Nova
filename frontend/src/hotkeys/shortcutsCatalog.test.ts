import { describe, expect, it } from 'vitest';
import { buildShortcutsCatalog } from './shortcutsCatalog';
import type { NovaActionRecord } from './novaActionTypes';

describe('buildShortcutsCatalog', () => {
  it('includes menu, automation, and enabled nova actions with rebind targets', () => {
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
    expect(sections.map((s) => s.id)).toEqual([
      'menu',
      'automation',
      'nova_actions',
    ]);
    expect(sections[0].rows[0].rebind).toEqual({ type: 'menu' });
    expect(sections[1].rows).toHaveLength(6);
    expect(sections[1].rows[0].rebind?.type).toBe('automation');
    expect(sections[2].rows[0].rebind).toEqual({ type: 'nova', id: 'a1' });
  });
});
