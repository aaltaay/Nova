import { describe, expect, it } from 'vitest';
import { findShortcutConflict } from './shortcutConflicts';

describe('findShortcutConflict', () => {
  const occupied = [
    {
      id: 'auto_kill_switch',
      label: 'Stop Automation',
      chord: { label: 'Ctrl+Shift+K', key: 'k', ctrl: true, shift: true },
    },
    {
      id: 'a1',
      label: 'Cancel symb',
      chord: { label: 'Ctrl+PageUp', key: 'PageUp', ctrl: true },
    },
  ];

  it('returns the other owner when chords collide', () => {
    const hit = findShortcutConflict(
      { label: 'Ctrl+Shift+K', key: 'k', ctrl: true, shift: true },
      occupied,
      'someone_else',
    );
    expect(hit?.id).toBe('auto_kill_switch');
  });

  it('ignores the row being edited', () => {
    const hit = findShortcutConflict(
      { label: 'Ctrl+Shift+K', key: 'k', ctrl: true, shift: true },
      occupied,
      'auto_kill_switch',
    );
    expect(hit).toBeNull();
  });
});
