/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { NewsHeadlineSection } from './NewsHeadlineSection';

const BENZINGA_HEADLINE =
  "12 Health Care Stocks Moving In Tuesday's After-Market Session";
const BENZINGA_URL =
  'https://www.benzinga.com/trading-ideas/movers/26/09/61805393/12-health-care-stocks-moving-tuesday-s-after-market-session';

describe('NewsHeadlineSection junk exclusion', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    root.unmount();
    container.remove();
  });

  it('hides a junk-only list and does not preview it', async () => {
    await act(() => {
      root.render(
        <NewsHeadlineSection
          news={[
            {
              headline: BENZINGA_HEADLINE,
              url: BENZINGA_URL,
              created_at: '2026-09-16T13:50:00Z',
              source: 'Benzinga',
            },
          ]}
          timeAgo={() => '10m'}
        />,
      );
    });
    expect(container.textContent).not.toContain('Health Care Stocks Moving');
    expect(container.querySelector('.cq-news-chip-flame')).toBeNull();
  });

  it('shows real news and keeps junk out of the preview', async () => {
    await act(() => {
      root.render(
        <NewsHeadlineSection
          news={[
            {
              headline: BENZINGA_HEADLINE,
              url: BENZINGA_URL,
              created_at: '2026-09-16T13:50:00Z',
              source: 'Benzinga',
            },
            {
              headline: 'UNH reports Q2 earnings miss',
              url: 'https://www.reuters.com/unh-earnings',
              created_at: '2026-09-16T12:00:00Z',
              source: 'Reuters',
            },
          ]}
          timeAgo={() => '2h'}
        />,
      );
    });
    expect(container.textContent).toContain('UNH reports Q2 earnings miss');
    expect(container.textContent).not.toContain('Health Care Stocks Moving');
  });
});
