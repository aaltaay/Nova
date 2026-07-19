import { describe, expect, it } from 'vitest';
import { createDefaultNovaActions } from './novaActionDefaults';

describe('createDefaultNovaActions', () => {
  it('includes cancel, panic cancel+flatten, exit, and Ask/Bid entry actions', () => {
    const actions = createDefaultNovaActions();
    const kinds = new Set(actions.map((a) => a.kind));
    expect(kinds.has('cancel_symbol')).toBe(true);
    expect(kinds.has('cancel_and_exit')).toBe(true);
    expect(kinds.has('exit_pos')).toBe(true);
    expect(kinds.has('exit_pos_pct')).toBe(true);
    expect(kinds.has('buy_limit_ask_offset')).toBe(true);
    expect(kinds.has('sell_limit_bid_offset')).toBe(true);
  });

  it('marks cancel / cancel+flatten / primary exits as showButton', () => {
    const actions = createDefaultNovaActions();
    const cancel = actions.find((a) => a.kind === 'cancel_symbol');
    const panic = actions.find((a) => a.kind === 'cancel_and_exit');
    expect(cancel?.showButton).toBe(true);
    expect(cancel?.enabled).toBe(true);
    expect(panic?.showButton).toBe(true);
    expect(panic?.key.label).toMatch(/Ctrl\+Shift\+Backspace/i);
  });
});

