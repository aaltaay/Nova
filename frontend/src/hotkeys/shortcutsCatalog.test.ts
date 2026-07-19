import { describe, expect, it } from 'vitest';
import { buildShortcutsCatalog } from './shortcutsCatalog';
import type { NovaActionRecord } from './novaActionTypes';

describe('buildShortcutsCatalog', () => {
  it('includes menu, automation, and enabled nova actions', () => {
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
      {
        id: 'a2',
        name: 'Off',
        kind: 'exit_pos',
        key: { label: 'Ctrl+Home', key: 'Home', ctrl: true },
        params: {},
        enabled: false,
        showButton: false,
      },
    ];
    const sections = buildShortcutsCatalog(actions);
    expect(sections.map((s) => s.id)).toEqual([
      'menu',
      'automation',
      'nova_actions',
    ]);
    expect(sections[0].rows[0].chord).toContain('Ctrl');
    expect(sections[1].rows).toHaveLength(6);
    expect(sections[2].rows).toHaveLength(1);
    expect(sections[2].rows[0].label).toBe('Cancel symb');
  });
});
