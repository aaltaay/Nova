/**
 * @vitest-environment jsdom
 *
 * Place while the padlock is locked runs the one unlock flow and stops there:
 * nothing is sent until the operator presses Place again.
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { TICKER_TRADE_UNLOCK_LABEL } from '../constants';
import { ManualOrderTicket } from './ManualOrderTicket';

const mocks = vi.hoisted(() => ({
  ensureUnlocked: vi.fn(async () => true),
  place: vi.fn(),
}));

vi.mock('./ticketUnlock', () => ({
  readTicketSessionUnlocked: () => false,
  subscribeTicketSessionUnlock: () => () => {},
}));
vi.mock('./useTradingPinGate', () => ({
  useTradingPinGate: () => ({ ensureUnlocked: mocks.ensureUnlocked, pinDialog: null }),
}));
vi.mock('./placeOrder', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./placeOrder')>()),
  placeIbkrOrder: mocks.place,
}));
vi.mock('./useIbkrStatus', () => ({
  useIbkrStatus: () => ({
    connected: true,
    mode: 'paper',
    spend_status: 'locked_disarmed',
    trading_allowed: false,
    trading_allowed_reason: 'Desk is disarmed',
    armed: false,
    arm_requires_pin: false,
  }),
}));

afterEach(() => {
  cleanup();
  mocks.ensureUnlocked.mockClear();
  mocks.place.mockClear();
});

describe('ManualOrderTicket while locked', () => {
  it('Place unlocks through the shared flow and does not send the order', async () => {
    render(
      <ManualOrderTicket
        symbol="SPY"
        mode="paper"
        connected
        spendStatus="locked_disarmed"
        summary={{ connected: true, mode: 'paper', NetLiquidation: 1000, BuyingPower: 1000 }}
        position={null}
        referencePrice={100}
      />,
    );
    const btn = screen.getByTestId('manual-order-submit') as HTMLButtonElement;
    expect(btn.textContent).toBe(TICKER_TRADE_UNLOCK_LABEL);
    expect(btn.disabled).toBe(false);

    await act(async () => { fireEvent.click(btn); await Promise.resolve(); });

    expect(mocks.ensureUnlocked).toHaveBeenCalledTimes(1);
    expect(mocks.place).not.toHaveBeenCalled();
  });
});
