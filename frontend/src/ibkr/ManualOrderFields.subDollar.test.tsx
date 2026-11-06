/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { ManualOrderFields } from './ManualOrderFields';
import type { ManualOrderType } from './orderEntry';

describe('ManualOrderFields price steps', () => {
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

  function step(orderType: ManualOrderType, id: string, prices: { limit?: string; stop?: string; reference?: number }) {
    const none = () => undefined;
    act(() => {
      root.render(
        <ManualOrderFields
          ticketSide="buy"
          allowShort={false}
          orderType={orderType}
          quantityMode="shares"
          quantityValue="1"
          limitPrice={prices.limit ?? ''}
          stopPrice={prices.stop ?? ''}
          referencePrice={prices.reference ?? null}
          outsideRth={false}
          disabled={false}
          onTicketSideChange={none}
          onOrderTypeChange={none}
          onQuantityModeChange={none}
          onQuantityValueChange={none}
          onLimitPriceChange={none}
          onStopPriceChange={none}
          onOutsideRthChange={none}
        />,
      );
    });
    return (container.querySelector(id) as HTMLInputElement).step;
  }

  it('lets a limit under $1 take four digits, and keeps cents from $1 up', () => {
    expect(step('LMT', '#manual-order-limit', { limit: '0.3188' })).toBe('0.0001');
    expect(step('LMT', '#manual-order-limit', { limit: '12.34' })).toBe('0.01');
  });

  it('does the same for a stop', () => {
    expect(step('STP', '#manual-order-stop', { stop: '0.3188' })).toBe('0.0001');
    expect(step('STP', '#manual-order-stop', { stop: '12.34' })).toBe('0.01');
  });

  it('moves a trail in the stock\'s tick, not its own size', () => {
    expect(step('TRAIL', '#manual-order-trail', { stop: '0.05', reference: 5.37 })).toBe('0.01');
    expect(step('TRAIL', '#manual-order-trail', { stop: '0.0037', reference: 0.37 })).toBe('0.0001');
  });
});
