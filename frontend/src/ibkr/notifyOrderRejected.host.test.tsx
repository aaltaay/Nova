/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AppDialogHost } from '../ux';
import { notifyOrderRejected } from './notifyOrderRejected';

const { acknowledgeIbkrVerification, openIbkrClientPortal } = vi.hoisted(() => ({
  acknowledgeIbkrVerification: vi.fn().mockResolvedValue(true),
  openIbkrClientPortal: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('./acknowledgeVerification', () => ({
  acknowledgeIbkrVerification,
}));
vi.mock('./openIbkrClientPortal', () => ({
  openIbkrClientPortal,
}));

describe('notifyOrderRejected pop-up', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    acknowledgeIbkrVerification.mockClear();
    openIbkrClientPortal.mockClear();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(
        <AppDialogHost>
          <div />
        </AppDialogHost>,
      );
    });
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it('opens a warning dialog for a buying-power reject', async () => {
    act(() => {
      notifyOrderRejected({
        message: 'estimated notional 596.54 exceeds BuyingPower 552.79',
        reasonCode: 'BUYING_POWER',
      });
    });
    expect(document.querySelector('[data-testid="app-dialog-title"]')?.textContent).toBe(
      'Not enough buying power',
    );
    expect(document.querySelector('[data-testid="app-dialog-message"]')?.textContent).toContain(
      '596.54',
    );
    expect(document.querySelector('[data-tone="warning"]')).toBeTruthy();

    await act(async () => {
      (document.querySelector('[data-testid="app-dialog-ok"]') as HTMLButtonElement).click();
      await Promise.resolve();
    });
    expect(document.querySelector('[data-testid="app-dialog"]')).toBeNull();
  });

  it('does not pop up when the operator cancelled the confirm', () => {
    act(() => {
      notifyOrderRejected({ message: 'Order cancelled' });
    });
    expect(document.querySelector('[data-testid="app-dialog"]')).toBeNull();
  });

  it('shows actionable verification controls and returns acknowledgment', async () => {
    let acknowledged: Promise<boolean>;
    act(() => {
      acknowledged = notifyOrderRejected({
        message: 'Order was not placed. IBKR requires Client Portal verification.',
        reasonCode: 'IBKR_VERIFICATION_REQUIRED',
        order: { symbol: 'AAPL', side: 'BUY', qty: 1, mode: 'live' },
      });
    });

    expect(document.querySelector('[data-testid="app-dialog-title"]')?.textContent).toBe(
      'Order not placed -- IBKR verification required',
    );
    expect(document.querySelector('[data-testid="app-dialog-message"]')?.textContent).toContain(
      'LIVE BUY 1 AAPL',
    );

    act(() => {
      (document.querySelector(
        '[data-testid="app-dialog-auxiliary"]',
      ) as HTMLButtonElement).click();
    });
    expect(openIbkrClientPortal).toHaveBeenCalledOnce();

    await act(async () => {
      (document.querySelector(
        '[data-testid="app-dialog-confirm"]',
      ) as HTMLButtonElement).click();
      await Promise.resolve();
    });
    await expect(acknowledged!).resolves.toBe(true);
    expect(acknowledgeIbkrVerification).toHaveBeenCalledWith('AAPL');
  });

  it('keeps the entry blocked when Nova cannot record acknowledgment', async () => {
    acknowledgeIbkrVerification.mockResolvedValueOnce(false);
    let acknowledged: Promise<boolean>;
    act(() => {
      acknowledged = notifyOrderRejected({
        message: 'Order was not placed. IBKR requires Client Portal verification.',
        reasonCode: 'IBKR_VERIFICATION_REQUIRED',
        order: { symbol: 'AAPL', side: 'BUY', qty: 1, mode: 'live' },
      });
    });

    await act(async () => {
      (document.querySelector(
        '[data-testid="app-dialog-confirm"]',
      ) as HTMLButtonElement).click();
      await Promise.resolve();
    });

    await expect(acknowledged!).resolves.toBe(false);
    expect(document.querySelector('[data-testid="app-dialog-title"]')?.textContent).toBe(
      'Verification acknowledgment failed',
    );
  });
});
