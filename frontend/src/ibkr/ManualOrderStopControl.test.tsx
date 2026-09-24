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

  it('shows the chosen stop type on the face, and a face click keeps it', () => {
    const { onOrderTypeChange } = render('STP LMT');
    const face = container.querySelector('[data-testid="manual-order-type-stop"]') as HTMLButtonElement;
    expect(face.textContent).toBe('Stop Limit');
    expect(face.getAttribute('aria-pressed')).toBe('true');
    act(() => face.click());
    expect(onOrderTypeChange).toHaveBeenCalledWith('STP LMT');

    render('TRAIL');
    expect(
      (container.querySelector('[data-testid="manual-order-type-stop"]') as HTMLButtonElement).textContent,
    ).toBe('Trail Stop');
  });

  it('lists all three stop types, checks the chosen one, and gets back to plain Stop', () => {
    const { onOrderTypeChange } = render('TRAIL');
    act(() => {
      (container.querySelector('[data-testid="manual-order-stop-caret"]') as HTMLButtonElement).click();
    });
    const items = Array.from(container.querySelectorAll('[role="menuitemradio"]'));
    expect(items.map(item => item.querySelector('.manual-order-stop-menu__label')?.textContent)).toEqual([
      'Stop',
      'Stop Limit',
      'Trailing Stop',
    ]);
    expect(items.map(item => item.getAttribute('aria-checked'))).toEqual(['false', 'false', 'true']);
    expect(document.activeElement).toBe(items[2]);
    act(() => {
      (container.querySelector('[data-testid="manual-order-stop-menu-stop"]') as HTMLButtonElement).click();
    });
    expect(onOrderTypeChange).toHaveBeenCalledWith('STP');
    expect(container.querySelector('[data-testid="manual-order-stop-flyout"]')).toBeNull();
  });

  it('moves through the menu with the arrow keys and closes on Escape', () => {
    render('STP');
    const caret = container.querySelector('[data-testid="manual-order-stop-caret"]') as HTMLButtonElement;
    act(() => caret.click());
    const items = Array.from(container.querySelectorAll<HTMLButtonElement>('[role="menuitemradio"]'));
    expect(document.activeElement).toBe(items[0]);
    const key = (name: string) =>
      act(() => {
        document.activeElement?.dispatchEvent(new KeyboardEvent('keydown', { key: name, bubbles: true }));
      });
    key('ArrowDown');
    expect(document.activeElement).toBe(items[1]);
    key('ArrowUp');
    key('ArrowUp');
    expect(document.activeElement).toBe(items[2]);
    key('Escape');
    expect(container.querySelector('[data-testid="manual-order-stop-flyout"]')).toBeNull();
    expect(document.activeElement).toBe(caret);
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
