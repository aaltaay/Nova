/**
 * @vitest-environment node
 */
import { describe, expect, it } from 'vitest';
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

  it('leaves the retired Automation chords free (ADR 025)', () => {
    const draft = action({
      id: 'x',
      name: 'X',
      key: { label: 'Shift+A', key: 'a', shift: true },
    });
    expect(novaActionConflictMessage(draft, [draft])).toBeNull();
  });
});
