/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ManualOrderFields } from './ManualOrderFields';
import type { ManualOrderType } from './orderEntry';

describe('ManualOrderFields Stop flyout', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
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

  function render(orderType: ManualOrderType = 'MKT') {
    const onOrderTypeChange = vi.fn();
    act(() => {
      root.render(
        <ManualOrderFields
          ticketSide="buy"
          allowShort={false}
          orderType={orderType}
          quantityMode="shares"
          quantityValue="1"
          limitPrice="10"
          stopPrice="9.5"
          outsideRth
          disabled={false}
          onTicketSideChange={() => undefined}
          onOrderTypeChange={onOrderTypeChange}
          onQuantityModeChange={() => undefined}
          onQuantityValueChange={() => undefined}
          onLimitPriceChange={() => undefined}
          onStopPriceChange={() => undefined}
          onOutsideRthChange={() => undefined}
        />,
      );
    });
    return { onOrderTypeChange };
  }

  it('keeps plain Stop one click and hides the flyout until the caret opens', () => {
    const { onOrderTypeChange } = render('MKT');
    expect(container.querySelector('[data-testid="manual-order-stop-flyout"]')).toBeNull();
    act(() => {
      (container.querySelector(
        '[data-testid="manual-order-type-stop"]',
      ) as HTMLButtonElement).click();
    });
    expect(onOrderTypeChange).toHaveBeenCalledWith('STP');
    expect(container.querySelector('#manual-order-stop')).toBeNull();
  });

  it('lists Stop Limit and Trailing Stop in the flyout', () => {
    const { onOrderTypeChange } = render('STP');
    act(() => {
      (container.querySelector(
        '[data-testid="manual-order-stop-caret"]',
      ) as HTMLButtonElement).click();
    });
    const flyout = container.querySelector('[data-testid="manual-order-stop-flyout"]');
    expect(flyout).toBeTruthy();
    expect(flyout?.textContent).toContain('Stop Limit');
    expect(flyout?.textContent).toContain('Trailing Stop');
    act(() => {
      (container.querySelector(
        '[data-testid="manual-order-type-stop-limit"]',
      ) as HTMLButtonElement).click();
    });
    expect(onOrderTypeChange).toHaveBeenCalledWith('STP LMT');
  });

  it('shows stop + limit fields for Stop Limit and trail $ for Trailing Stop', () => {
    render('STP LMT');
    expect(container.querySelector('#manual-order-stop')).toBeTruthy();
    expect(container.querySelector('#manual-order-limit')).toBeTruthy();
    expect(container.querySelector('#manual-order-trail')).toBeNull();

    act(() => {
      root.render(
        <ManualOrderFields
          ticketSide="sell"
          allowShort={false}
          orderType="TRAIL"
          quantityMode="shares"
          quantityValue="1"
          limitPrice=""
          stopPrice="0.35"
          outsideRth
          disabled={false}
          onTicketSideChange={() => undefined}
          onOrderTypeChange={() => undefined}
          onQuantityModeChange={() => undefined}
          onQuantityValueChange={() => undefined}
          onLimitPriceChange={() => undefined}
          onStopPriceChange={() => undefined}
          onOutsideRthChange={() => undefined}
        />,
      );
    });
    expect(container.querySelector('#manual-order-trail')).toBeTruthy();
    expect(container.textContent).toContain('Trail $');
    expect(container.querySelector('#manual-order-stop')).toBeNull();
  });

  it('selects Trailing Stop from the flyout', () => {
    const { onOrderTypeChange } = render('STP');
    act(() => {
      (container.querySelector(
        '[data-testid="manual-order-stop-caret"]',
      ) as HTMLButtonElement).click();
    });
    act(() => {
      (container.querySelector(
        '[data-testid="manual-order-type-trail"]',
      ) as HTMLButtonElement).click();
    });
    expect(onOrderTypeChange).toHaveBeenCalledWith('TRAIL');
  });
});
