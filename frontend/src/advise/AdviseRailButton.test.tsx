/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ScannerSideNav } from '../components/TabNav';

const openAdvise = vi.fn();

vi.mock('./AdviseContext', () => ({
  useAdviseOptional: () => ({
    open: false,
    openAdvise,
  }),
}));

describe('AdviseRailButton on the left rail', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    openAdvise.mockClear();
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it('renders Advise at the rail footer and does not change scanner tabs', () => {
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
    const button = container.querySelector(
      '[data-testid="scanner-nav-advise"]',
    ) as HTMLButtonElement;
    expect(button).toBeTruthy();
    expect(button.textContent).toMatch(/Advise/);
    act(() => {
      button.click();
    });
    expect(openAdvise).toHaveBeenCalled();
    expect(onTabClick).not.toHaveBeenCalled();
  });
});
