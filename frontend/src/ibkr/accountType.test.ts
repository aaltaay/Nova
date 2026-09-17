import { describe, expect, it } from 'vitest';
import { classifyMarginKind, shortSideVisible } from './accountType';
import type { IbkrAccountSummary } from './types';

function summary(overrides: Partial<IbkrAccountSummary> = {}): IbkrAccountSummary {
  return { connected: true, mode: 'live', ...overrides };
}

describe('classifyMarginKind / shortSideVisible', () => {
  it('treats Ahmed INDIVIDUAL + BP≈cash as Cash and hides Short', () => {
    const row = summary({
      AccountType: 'INDIVIDUAL',
      TradingType: 'STKNOPT',
      BuyingPower: 376,
      TotalCashValue: 383,
      NetLiquidation: 540,
    });
    expect(classifyMarginKind(row)).toBe('cash');
    expect(shortSideVisible(row)).toBe(false);
  });

  it('honors stamped account_class over local numbers', () => {
    const row = summary({
      account_class: 'margin',
      AccountType: 'INDIVIDUAL',
      BuyingPower: 376,
      TotalCashValue: 383,
    });
    expect(classifyMarginKind(row)).toBe('margin');
    expect(shortSideVisible(row)).toBe(true);
  });

  it('maps explicit tokens and BP leverage bands', () => {
    expect(classifyMarginKind(summary({ AccountType: 'MARGIN' }))).toBe('margin');
    expect(classifyMarginKind(summary({ BuyingPower: 200, TotalCashValue: 100 }))).toBe(
      'margin',
    );
    expect(classifyMarginKind(summary({ BuyingPower: 130, TotalCashValue: 100 }))).toBe(
      'cash',
    );
    expect(shortSideVisible(summary({ AccountType: 'MARGIN' }))).toBe(true);
  });

  it('hides Short when disconnected', () => {
    expect(
      shortSideVisible({ connected: false, mode: 'disconnected', AccountType: 'MARGIN' }),
    ).toBe(false);
    expect(shortSideVisible(null)).toBe(false);
  });
});
