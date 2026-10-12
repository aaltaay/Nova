/** @vitest-environment jsdom */
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import type { FundamentalsData } from '../types/ticker';
import { CountryFlag } from './CountryFlag';

const fund = (extra: Partial<FundamentalsData>) => ({ market_cap: null, float_shares: null, ...extra }) as FundamentalsData;

afterEach(cleanup);

describe('CountryFlag', () => {
  it("draws the headquarters country's flag and names it on hover", async () => {
    render(<CountryFlag fundamentals={fund({ country: 'Hong Kong', country_code: 'HK' })} />);
    const flag = screen.getByTestId('stock-view-quote-flag');
    expect(flag.getAttribute('title')).toBe('Headquarters: Hong Kong (Yahoo)');
    expect(flag.getAttribute('aria-label')).toBe('Headquarters: Hong Kong (Yahoo)');
    expect(flag.dataset.country).toBe('HK');
    // The flags load in their own chunk: an SVG, never a regional-indicator emoji Windows cannot draw.
    await waitFor(() => expect(flag.querySelector('svg')).not.toBeNull());
    expect(flag.textContent).toBe('');
  });

  it('says so with a dim globe when Yahoo gives no country', () => {
    render(<CountryFlag fundamentals={fund({ country: null, country_code: null })} />);
    const flag = screen.getByTestId('stock-view-quote-flag');
    expect(flag.getAttribute('title')).toBe('Country not known: Yahoo gives no headquarters country');
    expect(flag.classList.contains('sv-quote-card__flag--globe')).toBe(true);
    expect(flag.classList.contains('is-unknown')).toBe(true);
  });

  it('names a country it has no flag for on a globe, never guessing one', () => {
    render(<CountryFlag fundamentals={fund({ country: 'Netherlands Antilles', country_code: null })} />);
    const flag = screen.getByTestId('stock-view-quote-flag');
    expect(flag.getAttribute('title')).toBe('Headquarters: Netherlands Antilles (Yahoo)');
    expect(flag.classList.contains('sv-quote-card__flag--globe')).toBe(true);
    expect(flag.classList.contains('is-unknown')).toBe(false);
    expect(flag.dataset.country).toBeUndefined();
  });

  it('shows nothing before the fundamentals arrive', () => {
    const { container, rerender } = render(<CountryFlag fundamentals={null} />);
    expect(container.innerHTML).toBe('');
    // The fast first paint's `fundamentals: {}` is "not read yet", not "no country".
    rerender(<CountryFlag fundamentals={{} as FundamentalsData} />);
    expect(container.innerHTML).toBe('');
  });
});
