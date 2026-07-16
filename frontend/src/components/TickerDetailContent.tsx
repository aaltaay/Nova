/** Fundamentals + news + broker grid for a ticker; optional panel chart / stacked layout. */
import { TickerChart } from '../TickerChart';
import { DataSourcesPanel } from '../modules/DataSourcesPanel';
import { DepthTapePanel } from '../modules/DepthTapePanel';
import { FundamentalsPanel } from '../modules/FundamentalsPanel';
import { NewsPanel } from '../modules/NewsPanel';
import { QuoteHeaderPanel } from '../modules/QuoteHeaderPanel';
import { WatchlistStripPanel } from '../modules/WatchlistStripPanel';
import { computeQuoteMetrics } from '../modules/quoteMetrics';
import type { WatchlistEntry } from '../strategy/types';
import type { TickerDetail } from '../types/ticker';
import { fmtTimestamp } from '../utils/quoteFormat';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { useModuleVisibility } from '../workspace/useModuleVisibility';

interface Props {
  detail: TickerDetail;
  /**
   * Panel selection source of truth. Level 2 / live surfaces must bind to this,
   * never a stale detail.symbol from a previous ticker.
   */
  selectedSymbol?: string;
  /** When true, omit the quote header (symbol/price) — parent page already shows it. */
  hideHeader?: boolean;
  /** When true, render the panel-height chart (side panel). */
  showChart?: boolean;
  /** Side-by-side columns when width allows (quote | fundamentals under chart). */
  layout?: 'stack' | 'columns';
  /** Five Pillars / sub-scores for this symbol when ranked on the watchlist. */
  watchlistEntry?: WatchlistEntry | null;
}

export function TickerDetailContent({
  detail,
  selectedSymbol,
  hideHeader = false,
  showChart = false,
  layout = 'stack',
  watchlistEntry = null,
}: Props) {
  const { discoveryProvider } = useWorkspace();
  const { isVisible } = useModuleVisibility();
  const depthSymbol = (selectedSymbol ?? detail.symbol).toUpperCase();
  const trade = detail.snapshot?.latest_trade;
  const { lastUpdated } = computeQuoteMetrics(detail, discoveryProvider);
  const showQuote = isVisible('quote');
  const showNews = isVisible('news');
  const showCharts = isVisible('charts');

  const chartEl =
    showChart && showCharts ? (
      <TickerChart
        symbol={detail.symbol}
        variant="panel"
        lastTrade={
          trade?.price != null
            ? { price: trade.price, timestamp: trade.timestamp ?? null }
            : undefined
        }
      />
    ) : null;

  const bottomStamp = lastUpdated ? (
    <div className="cq-timestamp cq-timestamp-bottom">
      Last updated on {fmtTimestamp(lastUpdated)}
    </div>
  ) : null;

  if (layout === 'columns') {
    return (
      <div className="cq-root cq-root--stacked">
        <div className="cq-col cq-col--chart">{chartEl}</div>
        <WatchlistStripPanel entry={watchlistEntry} />
        <DepthTapePanel selectedSymbol={depthSymbol} detailSymbol={detail.symbol} />
        {showNews && <NewsPanel detail={detail} wrapped />}
        <div className="cq-info-row cq-info-row--two">
          <div className="cq-col cq-col--quote">
            {showQuote && <QuoteHeaderPanel detail={detail} hideHeader={hideHeader} />}
            <FundamentalsPanel detail={detail} variant="key" />
          </div>
          <div className="cq-col cq-col--fund">
            <FundamentalsPanel detail={detail} variant="fundamentals" showTitle />
            <DataSourcesPanel />
            {bottomStamp}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="cq-root">
      {showQuote && <QuoteHeaderPanel detail={detail} hideHeader={hideHeader} />}
      <DepthTapePanel selectedSymbol={depthSymbol} detailSymbol={detail.symbol} />
      {chartEl}
      {showNews && <NewsPanel detail={detail} />}
      <FundamentalsPanel detail={detail} variant="full" />
      <DataSourcesPanel />
      {bottomStamp}
    </div>
  );
}
