/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  GLOBAL_BAR_FUND_ACCOUNT_LABEL,
  GLOBAL_BAR_FUND_ACCOUNT_TITLE,
} from '../constants';
import { FundAccountButton } from './FundAccountButton';

const { openIbkrClientPortal } = vi.hoisted(() => ({
  openIbkrClientPortal: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('./openIbkrClientPortal', () => ({
  openIbkrClientPortal,
}));

describe('FundAccountButton', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    openIbkrClientPortal.mockClear();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(<FundAccountButton />);
    });
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it('opens IBKR Client Portal through the shared helper', () => {
    const button = container.querySelector(
      '[data-testid="global-bar-fund-account"]',
    ) as HTMLButtonElement;
    expect(button).toBeTruthy();
    expect(button.textContent).toBe(GLOBAL_BAR_FUND_ACCOUNT_LABEL);
    expect(button.title).toBe(GLOBAL_BAR_FUND_ACCOUNT_TITLE);
    expect(button.title.toLowerCase()).not.toMatch(/nova deposits|nova will deposit/);

    act(() => {
      button.click();
    });
    expect(openIbkrClientPortal).toHaveBeenCalledOnce();
  });
});
