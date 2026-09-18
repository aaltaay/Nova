/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { fireEvent } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TAPE_MIN_SIZE_STORAGE_KEY, TAPE_UI_MAX_ROWS } from '../constants';
import { TimeSalesPanel } from './TimeSalesPanel';
import type { TapePrint } from './tapeFeed';
import { writeTapeMinSize } from './tapeMinSizeFilter';

function makePrints(n: number, size = 100): TapePrint[] {
  return Array.from({ length: n }, (_, i) => ({
    symbol: 'AAPL',
    time: `2026-09-18T13:00:${String(59 - (i % 60)).padStart(2, '0')}.${String(i).padStart(3, '0')}Z`,
    price: n - i,
    size,
    exchange: 'ISLAND',
    side: 'ask' as const,
  }));
}

function mixedPrints(): TapePrint[] {
  return [10, 50, 100, 500].map((size, i) => ({
    symbol: 'QNME',
    time: `2026-09-18T15:33:3${i}.000Z`,
    price: 0.82,
    size,
    exchange: 'ISLAND',
    side: 'ask' as const,
  }));
}

const tapeMock = {
  prints: makePrints(TAPE_UI_MAX_ROWS),
  connected: true,
  error: null as string | null,
};

vi.mock('./useIbkrTape', () => ({
  useIbkrTape: () => tapeMock,
}));

function renderedSizes(root: ParentNode): number[] {
  return [...root.querySelectorAll('[data-testid="ts-size"]')].map((el) =>
    Number(el.getAttribute('data-size')),
  );
}

function openFilter(target: Element) {
  act(() => {
    target.dispatchEvent(
      new MouseEvent('contextmenu', {
        bubbles: true,
        cancelable: true,
        button: 2,
        clientX: 24,
        clientY: 36,
      }),
    );
  });
}

describe('TimeSalesPanel virtual window', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    localStorage.clear();
    tapeMock.prints = makePrints(TAPE_UI_MAX_ROWS);
    tapeMock.connected = true;
    tapeMock.error = null;
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    localStorage.clear();
  });

  it('keeps the full ring but mounts only a viewport window of rows', () => {
    act(() => {
      root.render(<TimeSalesPanel symbol="AAPL" />);
    });
    const rows = container.querySelector('[data-testid="ts-panel-rows"]');
    expect(rows?.getAttribute('data-ring-count')).toBe(String(TAPE_UI_MAX_ROWS));
    const rendered = Number(rows?.getAttribute('data-rendered-count'));
    expect(rendered).toBeGreaterThan(0);
    expect(rendered).toBeLessThan(TAPE_UI_MAX_ROWS);
    expect(container.querySelectorAll('.ts-row')).toHaveLength(rendered);
  });
});

describe('TimeSalesPanel min-size filter', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    localStorage.clear();
    tapeMock.prints = mixedPrints();
    tapeMock.connected = true;
    tapeMock.error = null;
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    localStorage.clear();
  });

  it('opens the filter UI from a right-click on the panel, header, or rows', () => {
    act(() => {
      root.render(<TimeSalesPanel symbol="QNME" />);
    });
    expect(document.querySelector('[data-testid="ts-min-size-filter"]')).toBeNull();

    openFilter(container.querySelector('[data-testid="ts-panel"]')!);
    expect(document.querySelector('[data-testid="ts-min-size-filter"]')).toBeTruthy();
    expect(document.querySelector('[data-testid="ts-min-size-input"]')).toBeTruthy();

    act(() => {
      document.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    });
    expect(document.querySelector('[data-testid="ts-min-size-filter"]')).toBeNull();

    openFilter(container.querySelector('.ts-panel__header')!);
    expect(document.querySelector('[data-testid="ts-min-size-filter"]')).toBeTruthy();
    act(() => {
      document.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    });

    openFilter(container.querySelector('[data-testid="ts-panel-rows"]')!);
    expect(document.querySelector('[data-testid="ts-min-size-filter"]')).toBeTruthy();
  });

  it('hides prints smaller than the typed min size', () => {
    act(() => {
      root.render(<TimeSalesPanel symbol="QNME" />);
    });
    openFilter(container.querySelector('[data-testid="ts-panel"]')!);
    const input = document.querySelector('[data-testid="ts-min-size-input"]') as HTMLInputElement;
    act(() => {
      fireEvent.change(input, { target: { value: '100' } });
    });
    expect(renderedSizes(container)).toEqual([100, 500]);
    expect(container.querySelector('[data-testid="ts-panel-rows"]')?.getAttribute('data-ring-count')).toBe('4');
    expect(container.querySelector('[data-testid="ts-panel-rows"]')?.getAttribute('data-filtered-count')).toBe('2');
    expect(container.querySelector('[data-testid="ts-min-size-badge"]')?.textContent).toBe('Size ≥ 100');
  });

  it('clears the filter when the box is empty or 0', () => {
    act(() => {
      root.render(<TimeSalesPanel symbol="QNME" />);
    });
    openFilter(container.querySelector('[data-testid="ts-panel"]')!);
    const input = document.querySelector('[data-testid="ts-min-size-input"]') as HTMLInputElement;
    act(() => {
      fireEvent.change(input, { target: { value: '100' } });
    });
    expect(renderedSizes(container)).toEqual([100, 500]);
    act(() => {
      fireEvent.change(input, { target: { value: '' } });
    });
    expect(renderedSizes(container)).toEqual([10, 50, 100, 500]);
    expect(container.querySelector('[data-testid="ts-min-size-badge"]')).toBeNull();
    expect(JSON.parse(localStorage.getItem(TAPE_MIN_SIZE_STORAGE_KEY) ?? '').value).toBe(0);
  });

  it('reloads the saved min size from localStorage on remount', () => {
    writeTapeMinSize(100);
    act(() => {
      root.render(<TimeSalesPanel symbol="QNME" />);
    });
    expect(container.querySelector('[data-testid="ts-min-size-badge"]')?.textContent).toBe('Size ≥ 100');
    expect(renderedSizes(container)).toEqual([100, 500]);

    act(() => {
      root.unmount();
    });
    root = createRoot(container);
    act(() => {
      root.render(<TimeSalesPanel symbol="QNME" />);
    });
    expect(container.querySelector('[data-testid="ts-min-size-badge"]')?.textContent).toBe('Size ≥ 100');
    expect(renderedSizes(container)).toEqual([100, 500]);
  });
});
