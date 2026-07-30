/**
 * @vitest-environment node
 */
import { describe, expect, it } from 'vitest';
import { HOTKEY_DEFAULTS } from '../constants';
import { formatHotkeyLabel } from '../hooks/hotkeyUtils';
import { novaActionConflictMessage } from './novaActionConflict';
import type { NovaActionRecord } from './novaActionTypes';

function action(
  partial: Partial<NovaActionRecord> & Pick<NovaActionRecord, 'id' | 'name' | 'key'>,
): NovaActionRecord {
  return {
    kind: 'cancel_symbol',
    params: {},
    enabled: true,
    showButton: false,
    ...partial,
  };
}

describe('novaActionConflictMessage', () => {
  it('returns null for empty key', () => {
    const a = action({ id: '1', name: 'A', key: { label: '', key: '' } });
    expect(novaActionConflictMessage(a, [a])).toBeNull();
  });

  it('detects conflict with another Nova Action', () => {
    const a = action({
      id: '1',
      name: 'A',
      key: { label: 'F1', key: 'F1' },
    });
    const b = action({
      id: '2',
      name: 'B',
      key: { label: 'F1', key: 'F1' },
    });
    expect(novaActionConflictMessage(b, [a, b])).toContain('A');
  });

  it('detects conflict with Automation default', () => {
    const b = HOTKEY_DEFAULTS.approve_staged;
    const draft = action({
      id: 'x',
      name: 'X',
      key: {
        label: formatHotkeyLabel(b),
        key: b.key,
        ctrl: b.ctrl,
        shift: b.shift,
        alt: b.alt,
        meta: b.meta,
      },
    });
    expect(novaActionConflictMessage(draft, [draft])).toMatch(
      /Conflicts with Automation shortcut/,
    );
  });
});
