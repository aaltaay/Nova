import { describe, expect, it } from 'vitest';
import {
  GLOBAL_BAR_ACCOUNT_TYPE_CASH,
  GLOBAL_BAR_ACCOUNT_TYPE_MARGIN,
  GLOBAL_BAR_ACCOUNT_TYPE_TOOLTIP,
  GLOBAL_BAR_ACCOUNT_TYPE_UNKNOWN,
} from '../constantGroups/global_bar';
import { accountTypeChipView, accountTypeTooltip } from './accountTypeChip';
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
    expect(view?.kind).toBe('cash');
    expect(view?.label).toBe(GLOBAL_BAR_ACCOUNT_TYPE_CASH);
    expect(view?.tooltip).toContain(GLOBAL_BAR_ACCOUNT_TYPE_TOOLTIP);
    expect(view?.tooltip).toContain('IBKR AccountType: CASH');
  });

  it('shows Margin only when AccountType or TradingType is a margin token', () => {
    const fromType = accountTypeChipView({
      ibkrConnected: true,
      summary: summary({ AccountType: 'MARGIN' }),
    });
    expect(fromType?.kind).toBe('margin');
    expect(fromType?.label).toBe(GLOBAL_BAR_ACCOUNT_TYPE_MARGIN);

    const fromTrading = accountTypeChipView({
      ibkrConnected: true,
      summary: summary({ AccountType: 'INDIVIDUAL', TradingType: 'CASH' }),
    });
    expect(fromTrading?.kind).toBe('cash');
  });

  it('keeps Ahmed live INDIVIDUAL snapshot as Unknown -- not Margin from BP', () => {
    const view = accountTypeChipView({
      ibkrConnected: true,
      summary: summary({
        AccountType: 'INDIVIDUAL',
        TradingType: 'STKNOPT',
        WhatIfPMEnabled: 'true',
        BuyingPower: 376,
        TotalCashValue: 383,
        NetLiquidation: 540,
        Leverage: 0.29,
      }),
    });
    expect(view?.kind).toBe('unknown');
    expect(view?.label).toBe(GLOBAL_BAR_ACCOUNT_TYPE_UNKNOWN);
    expect(view?.tooltip).toContain('IBKR AccountType: INDIVIDUAL');
    expect(view?.tooltip).toContain('IBKR TradingType-S: STKNOPT');
    expect(view?.tooltip).not.toMatch(/\bMargin\b/);
  });

  it('does not invent Margin from BuyingPower, WhatIfPMEnabled, or INDIVIDUAL', () => {
    const missingType = summary({ BuyingPower: 50_000 });
    const fromBp = accountTypeChipView({
      ibkrConnected: true,
      summary: missingType,
    });
    expect(fromBp?.kind).toBe('unknown');
    expect(accountTypeTooltip(missingType)).toContain('IBKR AccountType: (missing)');

    const fromPmFlag = accountTypeChipView({
      ibkrConnected: true,
      summary: summary({
        AccountType: 'INDIVIDUAL',
        WhatIfPMEnabled: 'true',
        BuyingPower: 50_000,
      }),
    });
    expect(fromPmFlag?.kind).toBe('unknown');
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
