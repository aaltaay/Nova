/** One timeframe at a time. Each cell is the desk's TickerChart for that pane. */

import { ChartFeedProvider, TickerChart } from '../chart';
import { CHART_DEFAULT_INDICATORS, CHART_GRID_PANE_INDICATORS, type ChartIndicatorId } from '../constants';
import type { ReviewPayload } from './reviewFixture';
import { feedFromPayload } from './reviewFeed';
import { levelOverlay } from './RecordedLevelsOverlay';
import { ReviewSymbolButton } from './ReviewSymbolButton';
import { GALLERY_TABS, TF_PANE, type ReviewQuery, type ReviewTf } from './reviewQuery';

export function GalleryBoard({
  query,
  gtf,
  payloads,
  onSelect,
  onPanePainted,
}: {
  query: ReviewQuery;
  gtf: ReviewTf;
  payloads: ReviewPayload[];
  onSelect: (tf: ReviewTf) => void;
  onPanePainted: (id: string) => void;
}) {
  const pane = TF_PANE[gtf];
  const indicators = [...(CHART_GRID_PANE_INDICATORS[pane.id] ?? CHART_DEFAULT_INDICATORS)] as ChartIndicatorId[];
  return (
    <div className="review-gallery">
      <div className="review-tabs" role="tablist">
        {GALLERY_TABS.map((tf) => (
          <button
            key={tf}
            type="button"
            role="tab"
            data-testid={`review-tab-${tf}`}
            aria-selected={gtf === tf}
            className={gtf === tf ? 'review-tab review-tab--on' : 'review-tab'}
            onClick={() => onSelect(tf)}
          >
            {tf}
          </button>
        ))}
      </div>
      <div className="review-gallery__cells">
        {payloads.map((payload) => {
          const feed = feedFromPayload(payload);
          return (
            <div className="review-cell" key={`${payload.symbol}-${gtf}`}>
              <ReviewSymbolButton symbol={payload.symbol} date={query.date} asOf={query.asOf} />
              <ChartFeedProvider feed={feed} onPanePainted={onPanePainted}>
                <TickerChart
                  symbol={payload.symbol}
                  variant="grid"
                  fixedTimeframe={pane.id}
                  title={pane.label}
                  indicators={indicators}
                  compactChrome
                  renderPaneOverlay={levelOverlay(payload.levels, payload.setups)}
                />
              </ChartFeedProvider>
            </div>
          );
        })}
      </div>
    </div>
  );
}
