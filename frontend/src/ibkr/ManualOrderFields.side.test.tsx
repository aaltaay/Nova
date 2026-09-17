/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  TICKER_TRADE_LABEL_BUY,
  TICKER_TRADE_LABEL_SELL,
  TICKER_TRADE_LABEL_SHORT,
} from '../constantGroups/shortability';
import { ManualOrderFields } from './ManualOrderFields';
import type { TicketSide } from './ticketSide';

describe('ManualOrderFields Side options', () => {
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

  function render(opts: {
    ticketSide?: TicketSide;
    allowShort?: boolean;
    shortDisabledReason?: string | null;
  } = {}) {
    const onTicketSideChange = vi.fn();
    act(() => {
      root.render(
        <ManualOrderFields
          ticketSide={opts.ticketSide ?? 'buy'}
          allowShort={opts.allowShort ?? false}
          orderType="MKT"
          quantityMode="shares"
          quantityValue="1"
          limitPrice=""
          stopPrice=""
          outsideRth
          disabled={false}
          shortDisabledReason={opts.shortDisabledReason ?? null}
          onTicketSideChange={onTicketSideChange}
          onOrderTypeChange={() => undefined}
          onQuantityModeChange={() => undefined}
          onQuantityValueChange={() => undefined}
          onLimitPriceChange={() => undefined}
          onStopPriceChange={() => undefined}
          onOutsideRthChange={() => undefined}
        />,
      );
    });
    return { onTicketSideChange };
  }

  it('hides Direction and Short on cash / unknown', () => {
    render({ allowShort: false });
    expect(container.textContent).not.toContain('Direction');
    expect(container.textContent).not.toContain('Long');
    expect(container.querySelector('[data-testid="manual-order-side-buy"]')?.textContent).toBe(
      TICKER_TRADE_LABEL_BUY,
    );
    expect(container.querySelector('[data-testid="manual-order-side-sell"]')?.textContent).toBe(
      TICKER_TRADE_LABEL_SELL,
    );
    expect(container.querySelector('[data-testid="manual-order-side-short"]')).toBeNull();
    expect(container.querySelector('.manual-order-direction')).toBeNull();
  });

  it('shows Buy / Sell / Short on margin and paints Short orange when selected', () => {
    render({ allowShort: true, ticketSide: 'short' });
    const short = container.querySelector(
      '[data-testid="manual-order-side-short"]',
    ) as HTMLButtonElement;
    expect(short).toBeTruthy();
    expect(short.textContent).toBe(TICKER_TRADE_LABEL_SHORT);
    expect(short.getAttribute('aria-pressed')).toBe('true');
    expect(short.classList.contains('is-short')).toBe(true);
    expect(
      container.querySelector('[data-testid="manual-order-side-sell"]')?.getAttribute(
        'aria-pressed',
      ),
    ).toBe('false');
  });

  it('does not treat Sell as a short open', () => {
    const { onTicketSideChange } = render({ allowShort: true, ticketSide: 'buy' });
    act(() => {
      (container.querySelector('[data-testid="manual-order-side-sell"]') as HTMLButtonElement).click();
    });
    expect(onTicketSideChange).toHaveBeenCalledWith('sell');
  });
});
