import { describe, expect, it } from 'vitest';
import {
  GLOBAL_BAR_ACCOUNT_TYPE_CASH,
  GLOBAL_BAR_ACCOUNT_TYPE_MARGIN,
  GLOBAL_BAR_ACCOUNT_TYPE_TOOLTIP,
  GLOBAL_BAR_ACCOUNT_TYPE_UNKNOWN,
} from '../constantGroups/global_bar';
import { accountTypeChipView } from './accountTypeChip';
import type { IbkrAccountSummary } from './types';

function summary(overrides: Partial<IbkrAccountSummary> = {}): IbkrAccountSummary {
  return {
    connected: true,
    mode: 'paper',
    NetLiquidation: 1000,
    BuyingPower: 4000,
    ...overrides,
  };
}

describe('accountTypeChipView', () => {
  it('shows Cash from IBKR AccountType and never from BuyingPower', () => {
    const view = accountTypeChipView({
      ibkrConnected: true,
      summary: summary({ AccountType: 'CASH', BuyingPower: 10 }),
    });
    expect(view).toEqual({
      kind: 'cash',
      label: GLOBAL_BAR_ACCOUNT_TYPE_CASH,
      tooltip: GLOBAL_BAR_ACCOUNT_TYPE_TOOLTIP,
    });
  });

  it('shows Margin only when AccountType is a margin token', () => {
    const view = accountTypeChipView({
      ibkrConnected: true,
      summary: summary({ AccountType: 'MARGIN' }),
    });
    expect(view?.kind).toBe('margin');
    expect(view?.label).toBe(GLOBAL_BAR_ACCOUNT_TYPE_MARGIN);
    expect(view?.tooltip).toBe(GLOBAL_BAR_ACCOUNT_TYPE_TOOLTIP);
  });

  it('does not invent Margin from BuyingPower or INDIVIDUAL structure', () => {
    const fromBp = accountTypeChipView({
      ibkrConnected: true,
      summary: summary({ BuyingPower: 50_000 }),
    });
    expect(fromBp?.kind).toBe('unknown');
    expect(fromBp?.label).toBe(GLOBAL_BAR_ACCOUNT_TYPE_UNKNOWN);

    const fromStructure = accountTypeChipView({
      ibkrConnected: true,
      summary: summary({ AccountType: 'INDIVIDUAL', BuyingPower: 50_000 }),
    });
    expect(fromStructure?.kind).toBe('unknown');
    expect(fromStructure?.label).toBe(GLOBAL_BAR_ACCOUNT_TYPE_UNKNOWN);
  });

  it('hides when disconnected or summary is missing', () => {
    expect(
      accountTypeChipView({
        ibkrConnected: false,
        summary: summary({ AccountType: 'MARGIN' }),
      }),
    ).toBeNull();
    expect(
      accountTypeChipView({
        ibkrConnected: true,
        summary: null,
      }),
    ).toBeNull();
    expect(
      accountTypeChipView({
        ibkrConnected: true,
        summary: { connected: false, mode: 'disconnected', AccountType: 'MARGIN' },
      }),
    ).toBeNull();
  });
});
