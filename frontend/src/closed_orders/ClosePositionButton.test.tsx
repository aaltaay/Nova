/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import * as closeMod from '../ibkr/closeFullPosition';
import { ClosePositionButton } from './ClosePositionButton';

const confirmAppMock = vi.fn();
const alertAppMock = vi.fn();

vi.mock('../ux', () => ({
  confirmApp: (...args: unknown[]) => confirmAppMock(...args),
  alertApp: (...args: unknown[]) => alertAppMock(...args),
}));

describe('ClosePositionButton', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    confirmAppMock.mockReset();
    alertAppMock.mockReset();
    confirmAppMock.mockResolvedValue(true);
    alertAppMock.mockResolvedValue(undefined);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.restoreAllMocks();
  });

  it('calls closeFullPosition (not cancel) after confirm', async () => {
    const spy = vi.spyOn(closeMod, 'closeFullPosition').mockResolvedValue({
      ok: true,
      order_id: 1,
      side: 'SELL',
      qty: 50,
    });
    const onClosed = vi.fn();
    act(() => {
      root.render(
        <ClosePositionButton
          position={{
            symbol: 'AAPL',
            qty: 50,
            market_price: 10,
            market_value: 500,
            avg_cost: 9,
            unrealized_pnl: 50,
            realized_pnl: 0,
          }}
          mode="paper"
          connected
          spendStatus="paper_armed"
          onClosed={onClosed}
        />,
      );
    });
    const btn = container.querySelector(
      '[data-testid="close-position-btn"]',
    ) as HTMLButtonElement;
    expect(btn.textContent).toMatch(/Flatten/);
    await act(async () => {
      btn.click();
    });
    expect(spy).toHaveBeenCalledWith(
      'AAPL',
      50,
      expect.objectContaining({
        referencePrice: 10,
        timingAction: expect.objectContaining({ source: 'user_action' }),
      }),
    );
    expect(onClosed).toHaveBeenCalled();
  });

  it('stays disabled when spend is locked', () => {
    act(() => {
      root.render(
        <ClosePositionButton
          position={{
            symbol: 'AAPL',
            qty: 10,
            market_price: 1,
            market_value: 10,
            avg_cost: 1,
            unrealized_pnl: 0,
            realized_pnl: 0,
          }}
          mode="paper"
          connected
          spendStatus="locked"
        />,
      );
    });
    const btn = container.querySelector(
      '[data-testid="close-position-btn"]',
    ) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it('stays disabled when accountError gate sets disabled', () => {
    act(() => {
      root.render(
        <ClosePositionButton
          position={{
            symbol: 'AAPL',
            qty: 10,
            market_price: 1,
            market_value: 10,
            avg_cost: 1,
            unrealized_pnl: 0,
            realized_pnl: 0,
          }}
          mode="paper"
          connected
          spendStatus="paper_armed"
          disabled
        />,
      );
    });
    const btn = container.querySelector(
      '[data-testid="close-position-btn"]',
    ) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });
});
