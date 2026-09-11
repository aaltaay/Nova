/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ManualOrderQuantityRow } from './ManualOrderQuantityRow';

describe('ManualOrderQuantityRow', () => {
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

  function render(value = '100') {
    const onQuantityModeChange = vi.fn();
    const onQuantityValueChange = vi.fn();
    act(() => {
      root.render(
        <ManualOrderQuantityRow
          quantityMode="shares"
          quantityValue={value}
          disabled={false}
          onQuantityModeChange={onQuantityModeChange}
          onQuantityValueChange={onQuantityValueChange}
        />,
      );
    });
    return { onQuantityModeChange, onQuantityValueChange };
  }

  it('keeps input, units, presets, and nudges in one row', () => {
    render();
    const row = container.querySelector('[data-testid="manual-order-quantity-row"]');
    expect(row).toBeTruthy();
    expect(row?.querySelector('#manual-order-quantity')).toBeTruthy();
    expect(row?.querySelector('[data-testid="manual-order-qty-mode-shares"]')).toBeTruthy();
    expect(row?.querySelector('.manual-order-presets')).toBeTruthy();
    expect(row?.querySelector('[data-testid="manual-order-qty-nudge-plus"]')).toBeTruthy();
    expect(row?.querySelector('[data-testid="manual-order-qty-nudge-minus"]')).toBeTruthy();
    expect(container.querySelectorAll('.manual-order-quantity-row').length).toBe(1);
  });

  it('nudges the current value with +1 and -1', () => {
    const { onQuantityValueChange } = render('100');
    act(() => {
      (container.querySelector(
        '[data-testid="manual-order-qty-nudge-plus"]',
      ) as HTMLButtonElement).click();
    });
    expect(onQuantityValueChange).toHaveBeenCalledWith('101');
    act(() => {
      (container.querySelector(
        '[data-testid="manual-order-qty-nudge-minus"]',
      ) as HTMLButtonElement).click();
    });
    expect(onQuantityValueChange).toHaveBeenCalledWith('99');
  });

  it('applies a share preset from the same row', () => {
    const { onQuantityValueChange } = render();
    const fifty = Array.from(container.querySelectorAll('.manual-order-presets button')).find(
      button => button.textContent === '50',
    ) as HTMLButtonElement;
    expect(fifty).toBeTruthy();
    act(() => {
      fifty.click();
    });
    expect(onQuantityValueChange).toHaveBeenCalledWith('50');
  });
});
