/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AdviseRailButton } from './AdviseRailButton';

const openAdvise = vi.fn();
const advise = vi.hoisted(() => ({ current: null as null | { open: boolean; openAdvise: () => void } }));

vi.mock('./AdviseContext', () => ({
  useAdviseOptional: () => advise.current,
}));

describe('AdviseRailButton on the nav rail foot', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    openAdvise.mockClear();
    advise.current = { open: false, openAdvise };
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it('renders as a rail item and opens Advise', () => {
    act(() => {
      root.render(<AdviseRailButton />);
    });
    const button = container.querySelector('[data-testid="nav-rail-advise"]') as HTMLButtonElement;
    expect(button).toBeTruthy();
    expect(button.classList.contains('nav-rail__item')).toBe(true);
    expect(button.textContent).toMatch(/Advise/);
    act(() => {
      button.click();
    });
    expect(openAdvise).toHaveBeenCalled();
  });

  it('stays off the rail without a provider', () => {
    advise.current = null;
    act(() => {
      root.render(<AdviseRailButton />);
    });
    expect(container.querySelector('[data-testid="nav-rail-advise"]')).toBeNull();
  });
});
