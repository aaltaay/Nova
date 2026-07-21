/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { TickerBrokerGrid } from './TickerBrokerGrid';
import type { ListingCompare } from '../types/ticker';

const listing: ListingCompare = {
  symbol: 'TEST',
  alpaca: {
    source: 'alpaca_assets',
    status: 'active',
    tradable: true,
    shortable: true,
    easy_to_borrow: true,
    short_type: 'easy_to_borrow',
    marginable: true,
    fractionable: false,
    attributes: [],
  },
  ibkr: {
    source: 'ibkr',
    connected: true,
    qualified: true,
    shortable_shares: 50_000,
    short_type: 'available',
    tradable_hint: 'qualified',
    stock_type: 'COMMON',
    long_name: 'Test Co',
  },
};

describe('TickerBrokerGrid', () => {
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

  it('renders Alpaca and IBKR columns side by side without merging', () => {
    act(() => {
      root.render(<TickerBrokerGrid asset={null} listing={listing} />);
    });
    const table = container.querySelector('[data-testid="listing-compare"]');
    expect(table?.textContent).toMatch(/Alpaca/);
    expect(table?.textContent).toMatch(/IBKR/);
    expect(table?.textContent).toMatch(/easy to borrow/);
    expect(table?.textContent).toMatch(/50,000/);
    expect(table?.textContent).toMatch(/qualified/);
    // Must not collapse to a single Yes/No for the whole section
    expect(table?.textContent).not.toMatch(/^Yes$/);
  });
});
