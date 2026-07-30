/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from 'vitest';
import { mergeMissingDefaultNovaActions } from './hotkeyStorage';
import type { NovaActionRecord } from './novaActionTypes';

function stub(id: string, kind: NovaActionRecord['kind']): NovaActionRecord {
  return {
    id,
    name: id,
    kind,
    key: { label: 'X', key: 'x' },
    params: {},
    enabled: true,
    showButton: false,
  };
}

describe('mergeMissingDefaultNovaActions', () => {
  it('adds all same-kind defaults by id (Webull % Ask rows)', () => {
    const existing = [stub('user-custom', 'exit_pos')];
    const merged = mergeMissingDefaultNovaActions(existing);
    const askIds = merged
      .filter((a) => a.id.startsWith('nova-wb-sell-') && a.kind === 'sell_pos_pct_ask')
      .map((a) => a.id)
      .sort();
    expect(askIds).toEqual([
      'nova-wb-sell-100-ask',
      'nova-wb-sell-25-ask',
      'nova-wb-sell-50-ask',
    ]);
  });

  it('does not overwrite an existing id', () => {
    const existing = [{
      ...stub('nova-wb-buy-1', 'buy_market'),
      name: 'My Buy',
      params: { shares: 5 },
    }];
    const merged = mergeMissingDefaultNovaActions(existing);
    const buy = merged.find((a) => a.id === 'nova-wb-buy-1');
    expect(buy?.name).toBe('My Buy');
    expect(buy?.params.shares).toBe(5);
  });
});
