/**
 * @vitest-environment jsdom
 */
import { act, type ReactNode } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { WorkspaceProvider } from '../workspace/WorkspaceContext';
import { QuoteHeaderPanel } from './QuoteHeaderPanel';
import { NewsPanel } from './NewsPanel';
import { FundamentalsPanel } from './FundamentalsPanel';
import { DataSourcesPanel } from './DataSourcesPanel';
import { WatchlistStripPanel } from './WatchlistStripPanel';
import { computeQuoteMetrics } from './quoteMetrics';
import { makeDetail } from './quoteFixtures';
import { TICKER_WATCHLIST_STRIP_EMPTY, QUOTE_CARD_TITLE } from '../constants';

vi.mock('../ibkr/useIbkrStatus', () => ({
  useIbkrStatus: () => ({
    enabled: true,
    connected: true,
    mode: 'paper',
    orders_enabled: false,
    spend_status: 'locked',
  }),
}));

function wrap(ui: ReactNode) {
  return <WorkspaceProvider>{ui}</WorkspaceProvider>;
}

describe('quoteMetrics', () => {
  it('computes IBKR unified price vs prev_close', () => {
    const m = computeQuoteMetrics(makeDetail(), 'ibkr');
    expect(m.mainPrice).toBe(190.5);
    expect(m.mainChangeAbs).toBeCloseTo(4.5);
    expect(m.isExtendedHours).toBe(false);
    expect(m.descParts.join(' | ')).toContain('Apple Inc');
  });

  it('handles empty snapshot gracefully', () => {
    const m = computeQuoteMetrics(
      makeDetail({
        snapshot: {
          latest_trade: null,
          latest_quote: null,
          minute_bar: null,
          daily_bar: null,
          prev_daily_bar: null,
          prev_close: null,
          session_close: null,
          session_prev_close: null,
        },
        fundamentals: null,
        asset: {},
      }),
      'ibkr',
    );
    expect(m.mainPrice).toBeNull();
    expect(m.gapPct).toBeNull();
    expect(m.descParts).toEqual([]);
  });
});

describe('QuoteHeaderPanel', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (String(url).includes('/api/config')) {
          return { ok: true, json: async () => ({ discovery_provider: 'ibkr', data_feed: 'sip' }) };
        }
        if (String(url).includes('blocklist')) {
          return { ok: true, json: async () => ({ symbols: [] }) };
        }
        return { ok: false, json: async () => ({}) };
      }),
    );
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.unstubAllGlobals();
  });

  it('renders symbol and price when populated', async () => {
    await act(async () => {
      root.render(wrap(<QuoteHeaderPanel detail={makeDetail()} />));
    });
    expect(container.querySelector('[data-module="quote-header"]')).toBeTruthy();
    expect(container.textContent).toContain(QUOTE_CARD_TITLE);
    expect(container.querySelector('.cq-symbol')?.textContent).toBe('AAPL');
    expect(container.querySelector('.cq-price')?.textContent).toBe('190.50');
  });

  it('hides price header when hideHeader', async () => {
    await act(async () => {
      root.render(wrap(<QuoteHeaderPanel detail={makeDetail()} hideHeader />));
    });
    expect(container.querySelector('.cq-price')).toBeNull();
    expect(container.querySelector('.cq-block-btn')).toBeTruthy();
  });
});

describe('NewsPanel', () => {
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

  it('marks empty news state', () => {
    act(() => {
      root.render(<NewsPanel detail={makeDetail({ news: [] })} />);
    });
    const el = container.querySelector('[data-module="news"]');
    expect(el?.getAttribute('data-news-empty')).toBe('true');
    expect(container.querySelector('.cq-news-section')).toBeNull();
  });

  it('renders headline when populated', () => {
    act(() => {
      root.render(
        <NewsPanel
          detail={makeDetail({
            news: [
              {
                headline: 'Apple beats estimates',
                summary: '',
                author: '',
                source: 'Reuters',
                url: 'https://example.com/n',
                created_at: new Date().toISOString(),
                symbols: ['AAPL'],
                images: [],
              },
            ],
          })}
        />,
      );
    });
    expect(container.querySelector('[data-module="news"]')?.getAttribute('data-news-empty')).toBe(
      'false',
    );
    expect(container.textContent).toContain('Apple beats estimates');
  });

  it('can omit impact when parent places bump elsewhere', () => {
    act(() => {
      root.render(
        <NewsPanel
          includeImpact={false}
          detail={makeDetail({
            news: [],
            news_impact: {
              symbol: 'AAPL',
              impact_class: 'moved_price',
              confidence: 0.8,
              rule_version: 'v1',
              headline: 'Earnings bump',
              summary: 'Price moved on news',
              age_hours: 1,
              age_bucket: 'fresh',
              source_name: 'benzinga',
              source_tier: 'official',
              confirmed_by_official: true,
              confirming_source_count: 1,
              price_reaction: 'strong',
              attention: 'unknown',
              l2_reaction: 'insufficient_data',
              sentiment: 'unavailable',
              sentiment_score: null,
              lexicon_sentiment: 'neutral',
              lexicon_polarity: 0,
              reasons: ['test'],
              factors: {},
              ai_reasoning: null,
              headline_url: null,
            },
          })}
        />,
      );
    });
    expect(container.querySelector('.news-impact-panel')).toBeNull();
    expect(container.querySelector('[data-module="news"]')?.getAttribute('data-news-empty')).toBe(
      'true',
    );
  });
});

describe('FundamentalsPanel', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        json: async () => ({ discovery_provider: 'ibkr', data_feed: 'sip' }),
      })),
    );
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.unstubAllGlobals();
  });

  it('key variant shows float/volume cells', async () => {
    await act(async () => {
      root.render(wrap(<FundamentalsPanel detail={makeDetail()} variant="key" />));
    });
    expect(container.querySelector('[data-variant="key"]')).toBeTruthy();
    expect(container.textContent).toContain('Float');
    expect(container.textContent).toContain('Volume');
  });

  it('full variant includes fundamentals fields', async () => {
    await act(async () => {
      root.render(wrap(<FundamentalsPanel detail={makeDetail()} variant="full" />));
    });
    expect(container.textContent).toContain('Market Cap');
    expect(container.textContent).toContain('Technology');
  });

  it('handles null fundamentals', async () => {
    await act(async () => {
      root.render(
        wrap(<FundamentalsPanel detail={makeDetail({ fundamentals: null })} variant="fundamentals" />),
      );
    });
    expect(container.textContent).toContain('Market Cap');
    expect(container.textContent).toContain('—');
  });
});

describe('DataSourcesPanel', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        json: async () => ({ discovery_provider: 'ibkr', data_feed: 'sip' }),
      })),
    );
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.unstubAllGlobals();
  });

  it('renders data sources section from workspace', async () => {
    await act(async () => {
      root.render(wrap(<DataSourcesPanel />));
    });
    expect(container.querySelector('[data-module="data-sources"]')).toBeTruthy();
    expect(container.querySelector('.cq-data-sources')).toBeTruthy();
  });
});

describe('WatchlistStripPanel', () => {
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

  it('shows empty copy when no entry', () => {
    act(() => {
      root.render(<WatchlistStripPanel entry={null} />);
    });
    expect(container.querySelector('[data-module="watchlist-strip"]')).toBeTruthy();
    expect(container.textContent).toContain(TICKER_WATCHLIST_STRIP_EMPTY);
  });
});
