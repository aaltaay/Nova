/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from 'vitest';
import {
  applyDeskAskBidHotkeys,
  deskAskBidEpochNeedsApply,
  mergeMissingDefaultNovaActions,
} from './hotkeyStorage';
import { DESK_ASK_BID_HOTKEY_EPOCH, DESK_ASK_BID_HOTKEY_EPOCH_KEY } from '../constants';
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

  it('rewrites Ask+/Bid- desk rows to F1/F2/F5 1-share EH and frees colliding F-keys', () => {
    const existing = [
      {
        ...stub('nova-buy-ask', 'buy_limit_ask_offset'),
        key: { label: 'Ctrl+Shift+B', key: 'B', ctrl: true, shift: true },
        params: { shares: 100, offsetDollars: 0.05 },
      },
      {
        ...stub('nova-sell-bid', 'sell_limit_bid_offset'),
        key: { label: 'Alt+Shift+S', key: 'S', alt: true, shift: true },
        params: { shares: 100, offsetDollars: 0.05 },
      },
      {
        ...stub('other-f1', 'buy_market'),
        key: { label: 'F1', key: 'F1' },
      },
      {
        ...stub('nova-sell-ask', 'sell_limit_ask_offset'),
        key: { label: 'X', key: 'x' },
        params: { shares: 100 },
      },
    ];
    const next = applyDeskAskBidHotkeys(existing);
    const buy = next.find((a) => a.id === 'nova-buy-ask');
    const sell = next.find((a) => a.id === 'nova-sell-bid');
    const sellAsk = next.find((a) => a.id === 'nova-sell-ask');
    const other = next.find((a) => a.id === 'other-f1');
    expect(buy?.key.label).toBe('F1');
    expect(buy?.params).toMatchObject({
      shares: 1,
      offsetDollars: 0.05,
      outsideRth: true,
    });
    expect(sell?.key.label).toBe('F2');
    expect(sell?.params.outsideRth).toBe(true);
    expect(sellAsk?.key.label).toBe('F5');
    expect(sellAsk?.params).toMatchObject({
      shares: 1,
      offsetDollars: 0.05,
      outsideRth: true,
    });
    expect(other?.key.key).toBe('');
  });

  it('knows when the desk F1/F2/F5 epoch still needs apply', () => {
    localStorage.removeItem(DESK_ASK_BID_HOTKEY_EPOCH_KEY);
    expect(deskAskBidEpochNeedsApply()).toBe(true);
    localStorage.setItem(DESK_ASK_BID_HOTKEY_EPOCH_KEY, DESK_ASK_BID_HOTKEY_EPOCH);
    expect(deskAskBidEpochNeedsApply()).toBe(false);
  });
});
