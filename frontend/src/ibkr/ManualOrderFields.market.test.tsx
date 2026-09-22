/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ManualOrderFields } from './ManualOrderFields';

const REASON = 'Market orders are not accepted outside regular hours -- use a limit at the ask';

describe('ManualOrderFields Market outside regular hours (MKT_OUTSIDE_RTH)', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  function render(marketDisabledReason: string | null) {
    const onOrderTypeChange = vi.fn();
    act(() => {
      root.render(
        <ManualOrderFields
          ticketSide="buy"
          allowShort={false}
          orderType="LMT"
          quantityMode="shares"
          quantityValue="1"
          limitPrice="8.86"
          stopPrice=""
          outsideRth
          disabled={false}
          marketDisabledReason={marketDisabledReason}
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

  it('greys Market out with the backend reason and never selects it', () => {
    const { onOrderTypeChange } = render(REASON);
    const btn = container.querySelector('[data-testid="manual-order-type-mkt"]') as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    expect(btn.title).toBe(REASON);
    act(() => btn.click());
    expect(onOrderTypeChange).not.toHaveBeenCalled();
    expect(container.querySelector('[data-testid="market-outside-rth-note"]')?.textContent).toBe(REASON);
  });

  it('leaves Market selectable in regular hours', () => {
    const { onOrderTypeChange } = render(null);
    const btn = container.querySelector('[data-testid="manual-order-type-mkt"]') as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
    act(() => btn.click());
    expect(onOrderTypeChange).toHaveBeenCalledWith('MKT');
    expect(container.querySelector('[data-testid="market-outside-rth-note"]')).toBeNull();
  });
});
