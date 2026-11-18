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

  it("reads IBKR's own TradingType-S word before any figure", () => {
    // The operator's Live cash account, 2026-11-17.
    const cash = summary({ AccountType: 'INDIVIDUAL', TradingType: 'STKCASH', BuyingPower: 5083.04, TotalCashValue: 5083.04, ExcessLiquidity: 5083.04 });
    expect(classifyMarginKind(cash)).toBe('cash');
    // A margin account with every dollar in use: no buying power left, still margin.
    const used = summary({ AccountType: 'INDIVIDUAL', TradingType: 'STKMRGN', BuyingPower: 0, TotalCashValue: -13_000, ExcessLiquidity: 0 });
    expect(classifyMarginKind(used)).toBe('margin');
    expect(shortSideVisible(used)).toBe(true);
  });

  it("keeps margin while a short's proceeds sit in cash", () => {
    const short = summary({ AccountType: 'INDIVIDUAL', TradingType: 'STKNOPT', BuyingPower: 11_600, TotalCashValue: 13_300, ExcessLiquidity: 2_900 });
    expect(classifyMarginKind(short)).toBe('margin');
    const borrowing = summary({ AccountType: 'INDIVIDUAL', BuyingPower: 14_000, TotalCashValue: -1_000, ExcessLiquidity: 3_500 });
    expect(classifyMarginKind(borrowing)).toBe('margin');
  });

  it('hides Short when disconnected', () => {
    expect(
      shortSideVisible({ connected: false, mode: 'disconnected', AccountType: 'MARGIN' }),
    ).toBe(false);
    expect(shortSideVisible(null)).toBe(false);
  });
});
