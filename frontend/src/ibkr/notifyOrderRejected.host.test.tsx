/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { AppDialogHost } from '../ux';
import { notifyOrderRejected } from './notifyOrderRejected';

describe('notifyOrderRejected pop-up', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
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
});
