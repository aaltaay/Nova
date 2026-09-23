/**
 * @vitest-environment jsdom
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import type { CatalystPanel } from '../types/catalystVerdict';
import { CatalystNewsSection } from './CatalystNewsSection';
import { NewsCell } from './NewsCell';

const now = Date.now() / 1000;
const panel: CatalystPanel = {
  schema_version: 1, symbol: 'BENF', generated_at: now, window_start: now - 18 * 3600, items_total: 2,
  verdict: {
    verdict: 'catalyst', category: 'listing_financing', strength: 'weak', rules_version: 'v5', negative_too: false,
    title: '8-K: Regulation FD | Beneficient Announces Strategy to Eliminate HCLP Debt and Heppner Equity Interests',
    source: 'edgar', published_ts: now - 3 * 3600, url: 'https://www.sec.gov/x', sources_answered: ['alpaca', 'edgar'],
    n_items: 2,
  },
  items: [
    { item_id: 'a:1', source: 'alpaca', publisher: 'benzinga', published_ts: now - 600, url: 'https://b/1',
      title: 'Dow Falls 100 Points; General Mills Posts Upbeat Q1 Earnings', kind: 'noise', category: 'movers_list',
      strength: null, dilution: false },
    { item_id: 'e:1', source: 'edgar', publisher: null, published_ts: now - 3 * 3600, url: 'https://www.sec.gov/x',
      title: '8-K: Regulation FD | Beneficient Announces Strategy to Eliminate HCLP Debt and Heppner Equity Interests',
      kind: 'catalyst', category: 'listing_financing', strength: 'weak', dilution: false },
  ],
};

afterEach(cleanup);

describe('CatalystNewsSection', () => {
  it('leads with the catalyst, never the newest market wrap', () => {
    render(<CatalystNewsSection panel={panel} />);
    const preview = screen.getByTitle(/Listing \/ financing: Beneficient Announces Strategy/);
    expect(preview.textContent).not.toContain('Dow Falls');
    expect(screen.getByText('1')).toBeTruthy(); // one company item
  });

  it('lists company items and folds movers lists / wraps away', () => {
    render(<CatalystNewsSection panel={panel} />);
    fireEvent.click(screen.getByRole('button', { name: /News/ }));
    expect(screen.getByText('Checked: Alpaca, SEC · 2 read')).toBeTruthy();
    expect(screen.queryByText(/Dow Falls/)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /1 movers lists \/ market wraps hidden/ }));
    expect(screen.getByText(/Dow Falls/)).toBeTruthy();
  });

  it('states an unread verdict and a failed read instead of "no news"', () => {
    const { rerender } = render(<CatalystNewsSection panel={null} loading />);
    expect(screen.getByText('Checking news since the prior close ...')).toBeTruthy();
    rerender(<CatalystNewsSection panel={null} error="News read failed: HTTP 500" />);
    expect(screen.getByText('News read failed: HTTP 500')).toBeTruthy();
  });
});

describe('NewsCell with a verdict', () => {
  it('gives a movers-list row no flame even when an article exists', () => {
    const { container } = render(
      <NewsCell newest_headline_at={new Date().toISOString()} catalyst={{ ...panel.verdict!, verdict: 'noise_only' }} />,
    );
    expect(container.querySelector('[data-news-mark="none"]')).toBeTruthy();
    expect(container.querySelector('.news-flame')).toBeNull();
  });

  it('flames a catalyst, marks dilution, and keeps the headline flame without the field', () => {
    const { container, rerender } = render(<NewsCell newest_headline_at={null} catalyst={panel.verdict} />);
    expect(container.querySelector('[data-news-mark="catalyst"].news-flame')).toBeTruthy();
    rerender(<NewsCell newest_headline_at={null} catalyst={{ ...panel.verdict!, verdict: 'negative', category: 'offering_dilution' }} />);
    expect(container.querySelector('[data-news-mark="negative"]')).toBeTruthy();
    rerender(<NewsCell newest_headline_at={new Date().toISOString()} />);
    expect(container.querySelector('.news-flame.flame-hot')).toBeTruthy();
  });
});
