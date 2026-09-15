/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ScannerSideNav } from './TabNav';

describe('ScannerSideNav', () => {
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

  it('renders rail items and marks Gappers active', () => {
    const onTabClick = vi.fn();
    act(() => {
      root.render(
        <ScannerSideNav
          activeTab="gappers"
          onTabClick={onTabClick}
          counts={{ gappers: 12, gainers: 5 }}
          visibility={{ gappers: true, gainers: true, losers: true }}
        />,
      );
    });
    expect(container.querySelector('[data-testid="scanner-side-nav"]')).toBeTruthy();
    const gappers = container.querySelector(
      '[data-testid="scanner-nav-gappers"]',
    ) as HTMLButtonElement;
    expect(gappers.classList.contains('is-active')).toBe(true);
    expect(gappers.textContent).toMatch(/Gappers/);
    expect(gappers.textContent).toMatch(/12/);
  });

  it('calls onTabClick when Gainers is selected', () => {
    const onTabClick = vi.fn();
    act(() => {
      root.render(
        <ScannerSideNav
          activeTab="gappers"
          onTabClick={onTabClick}
          counts={{}}
          visibility={{ gappers: true, gainers: true }}
        />,
      );
    });
    act(() => {
      (
        container.querySelector(
          '[data-testid="scanner-nav-gainers"]',
        ) as HTMLButtonElement
      ).click();
    });
    expect(onTabClick).toHaveBeenCalledWith('gainers');
  });

  it('keeps Advise off the rail without a provider', () => {
    act(() => {
      root.render(
        <ScannerSideNav
          activeTab="gappers"
          onTabClick={vi.fn()}
          counts={{}}
          visibility={{ gappers: true }}
        />,
      );
    });
    expect(container.querySelector('[data-testid="scanner-nav-advise"]')).toBeNull();
  });

  it('hides modules with visibility false', () => {
    act(() => {
      root.render(
        <ScannerSideNav
          activeTab="gappers"
          onTabClick={vi.fn()}
          counts={{}}
          visibility={{ gappers: true, gainers: false }}
        />,
      );
    });
    expect(container.querySelector('[data-testid="scanner-nav-gappers"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="scanner-nav-gainers"]')).toBeNull();
  });
});
