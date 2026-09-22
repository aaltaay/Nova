/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PracticeAccountSettings } from './PracticeAccountSettings';
import { TradeSettingsSection } from './TradeSettingsSection';

vi.mock('../practice/PracticeResetAction', () => ({
  PracticeResetAction: ({ venue }: { venue: string }) => (
    <div data-testid={`practice-reset-${venue}`}>{venue}</div>
  ),
}));

afterEach(cleanup);

describe('PracticeAccountSettings', () => {
  it('offers a reset per practice venue with the fake-money note', () => {
    render(<PracticeAccountSettings />);
    const section = screen.getByTestId('practice-account-settings');
    expect(section.textContent).toMatch(/Reset practice account/);
    expect(section.textContent).toMatch(/nothing reaches IBKR/);
    expect(screen.getByTestId('practice-reset-paper')).toBeTruthy();
    expect(screen.getByTestId('practice-reset-sim')).toBeTruthy();
  });

  it('is reachable from Settings > Trade as its own sub-tab', () => {
    render(<TradeSettingsSection />);
    expect(screen.queryByTestId('practice-account-settings')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Practice Account' }));
    expect(screen.getByTestId('practice-account-settings')).toBeTruthy();
  });
});
