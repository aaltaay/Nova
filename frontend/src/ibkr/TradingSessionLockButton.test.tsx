/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TICKER_TRADE_UNLOCK_PIN } from '../constants';
import { TradingSessionLockButton } from './TradingSessionLockButton';
import {
  readTicketSessionUnlocked,
  writeTicketSessionUnlocked,
} from './ticketUnlock';

const ibkrStatus = {
  connected: true,
  spend_status: 'paper_armed',
  spend_locked_reason: null as string | null,
  trading_allowed: true as boolean,
  trading_allowed_reason: null as string | null,
};

vi.mock('./useIbkrStatus', () => ({
  useIbkrStatus: () => ibkrStatus,
}));

vi.mock('./TradingPinDialog', () => ({
  TradingPinDialog: ({
    open,
    onSubmit,
  }: {
    open: boolean;
    onSubmit: (pin: string) => boolean;
  }) =>
    open ? (
      <button
        type="button"
        data-testid="mock-pin-submit"
        onClick={() => onSubmit(TICKER_TRADE_UNLOCK_PIN)}
      >
        submit pin
      </button>
    ) : null,
}));

describe('TradingSessionLockButton', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    sessionStorage.clear();
    ibkrStatus.connected = true;
    ibkrStatus.spend_status = 'paper_armed';
    ibkrStatus.trading_allowed = true;
    ibkrStatus.trading_allowed_reason = null;
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it('starts locked and unlocks via PIN dialog', async () => {
    act(() => {
      root.render(<TradingSessionLockButton />);
    });
    const btn = container.querySelector(
      '[data-testid="global-bar-trade-lock"]',
    ) as HTMLButtonElement;
    expect(btn.className).toMatch(/is-locked/);
    expect(readTicketSessionUnlocked()).toBe(false);

    await act(async () => {
      btn.click();
      await Promise.resolve();
    });
    await act(async () => {
      (container.querySelector('[data-testid="mock-pin-submit"]') as HTMLButtonElement).click();
      await Promise.resolve();
    });
    expect(readTicketSessionUnlocked()).toBe(true);
    expect(btn.className).toMatch(/is-unlocked/);
  });

  it('locks again on click when unlocked', async () => {
    writeTicketSessionUnlocked(true);
    act(() => {
      root.render(<TradingSessionLockButton />);
    });
    const btn = container.querySelector(
      '[data-testid="global-bar-trade-lock"]',
    ) as HTMLButtonElement;
    expect(btn.className).toMatch(/is-unlocked/);

    await act(async () => {
      btn.click();
      await Promise.resolve();
    });
    expect(readTicketSessionUnlocked()).toBe(false);
    expect(btn.className).toMatch(/is-locked/);
  });

  it('stays locked after PIN when backend trading_allowed is false', async () => {
    ibkrStatus.trading_allowed = false;
    ibkrStatus.trading_allowed_reason = 'Orders locked -- IBKR_ORDERS_ENABLED is off';
    writeTicketSessionUnlocked(true);
    act(() => {
      root.render(<TradingSessionLockButton />);
    });
    const btn = container.querySelector(
      '[data-testid="global-bar-trade-lock"]',
    ) as HTMLButtonElement;
    expect(readTicketSessionUnlocked()).toBe(true);
    expect(btn.className).toMatch(/is-locked/);
    expect(btn.className).not.toMatch(/is-unlocked/);
    expect(btn.title).toMatch(/ORDERS_ENABLED/);
  });
});
