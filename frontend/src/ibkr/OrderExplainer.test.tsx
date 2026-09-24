/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ManualOrderFields } from './ManualOrderFields';
import { OrderExplainerCard, placeExplainer } from './OrderExplainerCard';
import { ORDER_EXPLAINERS, type OrderExplainerKind } from './orderExplainerCopy';
import type { ManualOrderType } from './orderEntry';
import { EXPLAINER_HOVER_MS } from './useOrderExplainer';

function rect(left: number, top: number, width: number, height: number): DOMRect {
  return {
    left,
    top,
    width,
    height,
    right: left + width,
    bottom: top + height,
    x: left,
    y: top,
    toJSON: () => ({}),
  } as DOMRect;
}

describe('placeExplainer', () => {
  const card = { width: 292, height: 260 };
  const view = { width: 1600, height: 900 };

  it('sits left of a ticket docked on the right, centred on the control', () => {
    const spot = placeExplainer(rect(1320, 300, 90, 22), rect(1300, 100, 300, 600), card, view);
    expect(spot).toEqual({ side: 'left', left: 1300 - 10 - 292, top: 311 - 130 });
  });

  it('goes right of a ticket docked on the left', () => {
    const spot = placeExplainer(rect(20, 300, 90, 22), rect(0, 100, 300, 600), card, view);
    expect(spot.side).toBe('right');
    expect(spot.left).toBe(310);
  });

  it('stays inside the window vertically', () => {
    const spot = placeExplainer(rect(1320, 880, 90, 20), rect(1300, 100, 300, 800), card, view);
    expect(spot.top).toBe(900 - 8 - 260);
  });

  it('goes above the control when neither side has room', () => {
    const narrow = { width: 360, height: 900 };
    const spot = placeExplainer(rect(40, 400, 90, 22), rect(0, 0, 360, 900), card, narrow);
    expect(spot.side).toBe('above');
    expect(spot.top).toBe(400 - 10 - 260);
    expect(spot.left).toBeGreaterThanOrEqual(8);
    expect(spot.left + card.width).toBeLessThanOrEqual(360 - 8);
  });
});

describe('OrderExplainerCard', () => {
  afterEach(() => {
    document.body.innerHTML = '';
  });

  it.each(Object.keys(ORDER_EXPLAINERS) as OrderExplainerKind[])('draws %s with its words and chart', kind => {
    const anchor = document.createElement('button');
    document.body.appendChild(anchor);
    const host = document.createElement('div');
    document.body.appendChild(host);
    const root = createRoot(host);
    act(() => {
      root.render(<OrderExplainerCard id="x" kind={kind} anchor={anchor} onDismiss={() => undefined} />);
    });
    const card = document.querySelector('[data-testid="order-explainer"]') as HTMLElement;
    const copy = ORDER_EXPLAINERS[kind];
    expect(card.getAttribute('role')).toBe('tooltip');
    expect(card.textContent).toContain(copy.title);
    for (const fact of copy.facts) expect(card.textContent).toContain(fact);
    for (const item of copy.legend) expect(card.textContent).toContain(item.text);
    expect(card.querySelector(`[data-testid="order-explainer-art-${kind}"] path`)).toBeTruthy();
    act(() => root.unmount());
  });

  it('closes itself when its control is gone', () => {
    const anchor = document.createElement('button');
    const host = document.createElement('div');
    document.body.appendChild(host);
    const root = createRoot(host);
    const onDismiss = vi.fn();
    act(() => {
      root.render(<OrderExplainerCard id="x" kind="MKT" anchor={anchor} onDismiss={onDismiss} />);
    });
    expect(onDismiss).toHaveBeenCalled();
    act(() => root.unmount());
  });
});

describe('ManualOrderFields hover card', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    vi.useFakeTimers();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.useRealTimers();
  });

  function render(orderType: ManualOrderType = 'LMT') {
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
          onOrderTypeChange={() => undefined}
          onQuantityModeChange={() => undefined}
          onQuantityValueChange={() => undefined}
          onLimitPriceChange={() => undefined}
          onStopPriceChange={() => undefined}
          onOutsideRthChange={() => undefined}
        />,
      );
    });
  }

  const byId = (id: string) => container.querySelector(`[data-testid="${id}"]`) as HTMLElement;
  const card = () => document.querySelector('[data-testid="order-explainer"]') as HTMLElement | null;
  const enter = (el: HTMLElement) =>
    act(() => {
      el.dispatchEvent(new MouseEvent('pointerover', { bubbles: true, relatedTarget: null }));
    });
  const leave = (el: HTMLElement) =>
    act(() => {
      el.dispatchEvent(new MouseEvent('pointerout', { bubbles: true, relatedTarget: document.body }));
    });

  it('shows what Buy does after a short hover, and hides when the pointer leaves', () => {
    render();
    const buy = byId('manual-order-side-buy');
    enter(buy);
    expect(card()).toBeNull();
    act(() => vi.advanceTimersByTime(EXPLAINER_HOVER_MS));
    expect(card()?.dataset.kind).toBe('buy');
    expect(buy.getAttribute('aria-describedby')).toBe(card()?.id);
    leave(buy);
    act(() => vi.advanceTimersByTime(200));
    expect(card()).toBeNull();
  });

  it('follows the pointer from Sell to Market at once, and a press closes it', () => {
    render();
    enter(byId('manual-order-side-sell'));
    act(() => vi.advanceTimersByTime(EXPLAINER_HOVER_MS));
    expect(card()?.dataset.kind).toBe('sell');
    leave(byId('manual-order-side-sell'));
    enter(byId('manual-order-type-mkt'));
    expect(card()?.dataset.kind).toBe('MKT');
    act(() => {
      byId('manual-order-type-mkt').dispatchEvent(new MouseEvent('pointerdown', { bubbles: true }));
    });
    expect(card()).toBeNull();
  });

  it('explains the stop type on the face and each type in the menu', () => {
    render('STP LMT');
    enter(byId('manual-order-type-stop'));
    act(() => vi.advanceTimersByTime(EXPLAINER_HOVER_MS));
    expect(card()?.dataset.kind).toBe('STP LMT');
    leave(byId('manual-order-type-stop'));
    act(() => vi.advanceTimersByTime(200));

    act(() => (byId('manual-order-stop-caret') as HTMLButtonElement).click());
    enter(byId('manual-order-type-trail'));
    act(() => vi.advanceTimersByTime(EXPLAINER_HOVER_MS));
    expect(card()?.dataset.kind).toBe('TRAIL');
    expect(card()?.textContent).toContain('Trailing stop order');
  });

  it('puts no native tooltip on the explained controls', () => {
    render('STP');
    for (const id of [
      'manual-order-side-buy',
      'manual-order-side-sell',
      'manual-order-type-lmt',
      'manual-order-type-mkt',
      'manual-order-type-stop',
    ]) {
      expect(byId(id).hasAttribute('title'), id).toBe(false);
    }
  });
});
