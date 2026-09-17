/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TICKER_TRADE_LABEL_TRADING_HOURS } from '../constants';
import { ManualOrderFields } from './ManualOrderFields';
import type { ManualOrderType } from './orderEntry';

describe('ManualOrderFields Extended Hours checkbox', () => {
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

  function render(orderType: ManualOrderType, outsideRth = true) {
    const onOutsideRthChange = vi.fn();
    act(() => {
      root.render(
        <ManualOrderFields
          ticketSide="buy"
          allowShort={false}
          orderType={orderType}
          quantityMode="shares"
          quantityValue="1"
          limitPrice=""
          stopPrice="10"
          outsideRth={outsideRth}
          disabled={false}
          onTicketSideChange={() => undefined}
          onOrderTypeChange={() => undefined}
          onQuantityModeChange={() => undefined}
          onQuantityValueChange={() => undefined}
          onLimitPriceChange={() => undefined}
          onStopPriceChange={() => undefined}
          onOutsideRthChange={onOutsideRthChange}
        />,
      );
    });
    return { onOutsideRthChange };
  }

  function checkbox(): HTMLInputElement {
    return container.querySelector(
      '[data-testid="manual-order-extended"]',
    ) as HTMLInputElement;
  }

  it('renders an enabled Extended Hours checkbox default-checked for Market', () => {
    render('MKT', true);
    const box = checkbox();
    expect(box).toBeTruthy();
    expect(box.type).toBe('checkbox');
    expect(box.checked).toBe(true);
    expect(box.disabled).toBe(false);
    expect(container.querySelector('#manual-order-hours')).toBeNull();
    expect(container.textContent).toContain(TICKER_TRADE_LABEL_TRADING_HOURS);
  });

  it('does not disable the checkbox for Stop', () => {
    render('STP', true);
    const box = checkbox();
    expect(box.disabled).toBe(false);
    expect(box.checked).toBe(true);
  });

  it('toggles Extended Hours for Market', () => {
    const { onOutsideRthChange } = render('MKT', true);
    act(() => {
      checkbox().click();
    });
    expect(onOutsideRthChange).toHaveBeenCalledWith(false);
  });
});
