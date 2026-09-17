/**
 * @vitest-environment jsdom
 */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import {
  GLOBAL_BAR_ACCOUNT_TYPE_CASH,
  GLOBAL_BAR_ACCOUNT_TYPE_MARGIN,
  GLOBAL_BAR_ACCOUNT_TYPE_TOOLTIP,
} from '../constantGroups/global_bar';
import { IbkrAccountTypeChip } from './IbkrAccountTypeChip';
import type { IbkrAccountSummary } from './types';

afterEach(() => cleanup());

function summary(overrides: Partial<IbkrAccountSummary> = {}): IbkrAccountSummary {
  return {
    connected: true,
    mode: 'paper',
    ...overrides,
  };
}

describe('IbkrAccountTypeChip', () => {
  it('renders Cash from AccountType', () => {
    render(
      <IbkrAccountTypeChip
        ibkrConnected
        summary={summary({ AccountType: 'cash' })}
      />,
    );
    const chip = screen.getByTestId('global-bar-account-type');
    expect(chip.textContent).toBe(GLOBAL_BAR_ACCOUNT_TYPE_CASH);
    expect(chip.getAttribute('data-kind')).toBe('cash');
    expect(chip.getAttribute('title') ?? '').toContain(GLOBAL_BAR_ACCOUNT_TYPE_TOOLTIP);
    expect(chip.getAttribute('title') ?? '').toContain('IBKR AccountType: cash');
  });

  it('renders Margin from AccountType', () => {
    render(
      <IbkrAccountTypeChip
        ibkrConnected
        summary={summary({ AccountType: 'MARGIN' })}
      />,
    );
    const chip = screen.getByTestId('global-bar-account-type');
    expect(chip.textContent).toBe(GLOBAL_BAR_ACCOUNT_TYPE_MARGIN);
    expect(chip.getAttribute('data-kind')).toBe('margin');
    expect(chip.getAttribute('title')).toMatch(/IBKR_SHORT_ENABLED/);
    expect(chip.getAttribute('title') ?? '').toContain('IBKR AccountType: MARGIN');
  });

  it('renders Cash when connected and AccountType is INDIVIDUAL', () => {
    render(
      <IbkrAccountTypeChip
        ibkrConnected
        summary={summary({ AccountType: 'INDIVIDUAL', BuyingPower: 376, TotalCashValue: 383 })}
      />,
    );
    const chip = screen.getByTestId('global-bar-account-type');
    expect(chip.textContent).toBe(GLOBAL_BAR_ACCOUNT_TYPE_CASH);
    expect(chip.getAttribute('data-kind')).toBe('cash');
    expect(chip.getAttribute('title') ?? '').toContain('IBKR AccountType: INDIVIDUAL');
  });

  it('renders Cash when connected but AccountType is missing', () => {
    render(<IbkrAccountTypeChip ibkrConnected summary={summary()} />);
    const chip = screen.getByTestId('global-bar-account-type');
    expect(chip.textContent).toBe(GLOBAL_BAR_ACCOUNT_TYPE_CASH);
    expect(chip.getAttribute('data-kind')).toBe('cash');
    expect(chip.getAttribute('title') ?? '').toContain('IBKR AccountType: (missing)');
  });

  it('hides when Gateway is disconnected', () => {
    const { container } = render(
      <IbkrAccountTypeChip
        ibkrConnected={false}
        summary={summary({ AccountType: 'MARGIN' })}
      />,
    );
    expect(container.querySelector('[data-testid="global-bar-account-type"]')).toBeNull();
  });
});
