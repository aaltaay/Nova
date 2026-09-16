/**
 * @vitest-environment jsdom
 */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { MwcbBanner } from './MwcbBanner';

afterEach(() => cleanup());

describe('MwcbBanner', () => {
  it('hides when there is no market-wide halt', () => {
    const { container } = render(<MwcbBanner mwcb={null} />);
    expect(container.querySelector('[data-testid="mwcb-banner"]')).toBeNull();
  });

  it('shows a desk-wide Level 2 banner that is not a Place control', () => {
    render(<MwcbBanner mwcb={{ level: 2, reason_code: 'MWC2' }} />);
    const banner = screen.getByTestId('mwcb-banner');
    expect(banner.textContent).toMatch(/Level 2/);
    expect(banner.textContent).toMatch(/MWC2/);
    expect(banner.getAttribute('data-level')).toBe('2');
    expect(banner.tagName.toLowerCase()).toBe('div');
    expect(banner.closest('button')).toBeNull();
  });
});
