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

describe('CatalystNewsSection on a Sim replay desk (operator report, 2026-10-12)', () => {
  // 2026-07-15 07:20:26 ET, the replayed playhead.
  const at = Date.UTC(2026, 6, 15, 11, 20, 26) / 1000;

  it("says which moment the news is from and ages items against the playhead, not the wall clock", () => {
    const replay: CatalystPanel = {
      ...panel, generated_at: at, window_start: at - 15 * 3600,
      verdict: { ...panel.verdict!, published_ts: at - 900 },
      items: [{ ...panel.items[1], published_ts: at - 900 }],
      items_total: 1,
      replay: { session_date: '2026-07-15', at, on_file: true },
    };
    render(<CatalystNewsSection panel={replay} />);
    fireEvent.click(screen.getByRole('button', { name: /News/ }));
    expect(screen.getByTestId('cn-replay').textContent).toBe("As known at Jul 15 07:20 ET -- the catalyst backfill's items");
    expect(screen.getAllByText(/15m ago/).length).toBeGreaterThan(0);
  });

  it(`states a day with no news on file as unknown, never today's news or "checking"`, () => {
    const offFile: CatalystPanel = {
      schema_version: 1, symbol: 'GRML', generated_at: at, window_start: at - 15 * 3600, verdict: null,
      items: [], items_total: 0, replay: { session_date: '2026-07-15', at, on_file: false },
    };
    render(<CatalystNewsSection panel={offFile} />);
    const line = `No news on file for GRML on Jul 15: unknown, not "no news". Today's news is not shown on a replay.`;
    expect(screen.getByTitle(line).textContent).toBe(line);
    fireEvent.click(screen.getByRole('button', { name: /News/ }));
    expect(screen.getByTestId('cn-replay').textContent).toBe(line);
    expect(screen.queryByText('Checking news since the prior close ...')).toBeNull();
    expect(screen.queryByText('No company items since the prior close')).toBeNull();
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

describe('CatalystNewsSection: the prior session (rules v8)', () => {
  it("names the prior session's release beside a no-catalyst verdict, never as the verdict", () => {
    const amod: CatalystPanel = {
      ...panel, symbol: 'AMOD', items: [], items_total: 0,
      verdict: {
        verdict: 'noise_only', category: null, strength: null, rules_version: 'catalyst-rules-v8-2026-10-02',
        title: null, source: null, published_ts: null, url: null, negative_too: false, sources_answered: ['alpaca'],
        prior_session: {
          kind: 'catalyst', category: 'crypto_treasury', strength: 'weak', dilution: true, source: 'edgar',
          title: '8-K: Acquisition completed; Other events', published_ts: now - 21 * 3600, url: 'https://www.sec.gov/amod',
        },
      },
    };
    render(<CatalystNewsSection panel={amod} />);
    fireEvent.click(screen.getByRole('button', { expanded: false }));
    const prior = screen.getByTestId('cn-verdict-prior');
    expect(prior.textContent).toContain('Before the prior close (not counted today)');
    expect(prior.textContent).toContain('Crypto treasury raise (weak): 8-K: Acquisition completed; Other events · SEC · 21h ago');
    expect(screen.getByText(/Only movers lists/)).toBeTruthy();
  });
});
