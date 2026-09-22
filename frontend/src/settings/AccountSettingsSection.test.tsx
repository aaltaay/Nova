/**
 * @vitest-environment jsdom
 *
 * Settings > Account (QA V35, 2026-09-22): spend state in words, and a door to
 * the Account page rather than the legacy Trading tab.
 */
import { act } from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { getNavPage, resetNavRailStoreForTests } from '../workspace/navRailStore';
import { AccountSettingsSection } from './AccountSettingsSection';

const mocks = vi.hoisted(() => ({
  status: { connected: true, mode: 'paper', venue: 'paper', spend_status: 'locked_disarmed' } as Record<string, unknown>,
  showScannerView: vi.fn(),
  traderViewActive: false,
}));

vi.mock('../ibkr/useIbkrStatus', () => ({ useIbkrStatus: () => mocks.status }));
vi.mock('../workspace/WorkspaceContext', () => ({
  useWorkspace: () => ({ traderViewActive: mocks.traderViewActive, showScannerView: mocks.showScannerView }),
}));

beforeEach(() => {
  resetNavRailStoreForTests();
  mocks.showScannerView.mockReset();
  mocks.traderViewActive = false;
});

afterEach(cleanup);

describe('AccountSettingsSection', () => {
  it('reads the spend state in words, never the raw token', () => {
    render(<AccountSettingsSection onClose={() => {}} />);
    const orders = screen.getByTestId('settings-account-orders');
    expect(orders.textContent).toBe('DISARMED — arm to trade');
    expect(orders.textContent).not.toContain('locked_disarmed');
    expect(screen.getByTestId('settings-account').textContent).toContain('Paper (Nova practice account)');
  });

  it('opens the Account page from the Trader too, and closes Settings', () => {
    mocks.traderViewActive = true;
    const onClose = vi.fn();
    render(<AccountSettingsSection onClose={onClose} />);
    const door = screen.getByTestId('settings-account-open-account');
    expect(door.textContent).toBe('Open Account page');
    act(() => door.click());
    expect(getNavPage()).toBe('account');
    expect(mocks.showScannerView).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });
});
