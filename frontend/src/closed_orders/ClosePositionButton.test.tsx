/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import {
  CLOSE_POSITION_ACCOUNT_ERROR_TITLE,
  CLOSE_POSITION_BUSY_WHY,
  CLOSE_POSITION_NO_POSITION_TITLE,
  CLOSE_POSITION_STALE_WHY,
  WHY_GATEWAY_NOT_CONNECTED,
} from '../constants';
import * as closeMod from '../ibkr/closeFullPosition';
import { spendLockReason } from '../ibkr/spendLock';
import type { IbkrMode } from '../ibkr/types';
import { ClosePositionButton } from './ClosePositionButton';

const confirmAppMock = vi.fn();
const alertAppMock = vi.fn();
const ensureUnlockedMock = vi.fn(async () => true);

vi.mock('../ux', () => ({
  confirmApp: (...args: unknown[]) => confirmAppMock(...args),
  alertApp: (...args: unknown[]) => alertAppMock(...args),
}));

vi.mock('../ibkr/useTradingPinGate', () => ({
  useTradingPinGate: () => ({
    ensureUnlocked: (...args: unknown[]) => ensureUnlockedMock(...args),
    pinDialog: null,
  }),
}));

vi.mock('../ibkr/ticketUnlock', () => ({
  readTicketSessionUnlocked: () => true,
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
    ensureUnlockedMock.mockReset();
    ensureUnlockedMock.mockResolvedValue(true);
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
    // The lock says why (ux/whyTip.ts), and no native title stacks on it.
    expect(btn.dataset.why).toBe(spendLockReason('locked'));
    expect(btn.hasAttribute('title')).toBe(false);
  });

  it('does not flatten when PIN unlock is cancelled', async () => {
    ensureUnlockedMock.mockResolvedValue(false);
    const spy = vi.spyOn(closeMod, 'closeFullPosition');
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
        />,
      );
    });
    await act(async () => {
      (container.querySelector('[data-testid="close-position-btn"]') as HTMLButtonElement).click();
    });
    expect(ensureUnlockedMock).toHaveBeenCalled();
    expect(confirmAppMock).not.toHaveBeenCalled();
    expect(spy).not.toHaveBeenCalled();
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
    expect(btn.dataset.why).toBe(CLOSE_POSITION_ACCOUNT_ERROR_TITLE);
  });

  describe('says why it is locked', () => {
    const POSITION = {
      symbol: 'AAPL', qty: 10, market_price: 1, market_value: 10, avg_cost: 1, unrealized_pnl: 0, realized_pnl: 0,
    };

    function renderButton(props: {
      qty?: number; mode?: IbkrMode; connected?: boolean; disabled?: boolean; why?: string | null;
    }) {
      act(() => {
        root.render(
          <ClosePositionButton
            position={{ ...POSITION, qty: props.qty ?? POSITION.qty }}
            mode={props.mode ?? 'paper'}
            connected={props.connected ?? true}
            spendStatus="paper_armed"
            disabled={props.disabled}
            why={props.why}
          />,
        );
      });
      return container.querySelector('[data-testid="close-position-btn"]') as HTMLButtonElement;
    }

    it('names the caller\'s reason for its lock', () => {
      const btn = renderButton({ disabled: true, why: CLOSE_POSITION_STALE_WHY });
      expect(btn.dataset.why).toBe(CLOSE_POSITION_STALE_WHY);
    });

    it('names a flat position and a missing Gateway', () => {
      expect(renderButton({ qty: 0 }).dataset.why).toBe(CLOSE_POSITION_NO_POSITION_TITLE);
      expect(renderButton({ connected: false }).dataset.why).toBe(WHY_GATEWAY_NOT_CONNECTED);
      expect(renderButton({ mode: 'disconnected' }).dataset.why).toBe(WHY_GATEWAY_NOT_CONNECTED);
    });

    it('names its own flatten while it is in flight, and carries no reason when it can act', async () => {
      let answer!: (value: Awaited<ReturnType<typeof closeMod.closeFullPosition>>) => void;
      vi.spyOn(closeMod, 'closeFullPosition').mockImplementation(
        () => new Promise((resolve) => { answer = resolve; }),
      );
      const btn = renderButton({});
      expect(btn.disabled).toBe(false);
      expect(btn.dataset.why).toBeUndefined();
      expect(btn.title).toMatch(/Flatten closes the entire position/);
      await act(async () => {
        btn.click();
      });
      expect(btn.disabled).toBe(true);
      expect(btn.dataset.why).toBe(CLOSE_POSITION_BUSY_WHY);
      await act(async () => {
        answer({ ok: true, order_id: 1, side: 'SELL', qty: 10, outside_rth: false, order_type: 'MKT' });
      });
      expect(btn.disabled).toBe(false);
      expect(btn.dataset.why).toBeUndefined();
    });
  });
});
