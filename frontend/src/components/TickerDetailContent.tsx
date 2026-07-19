/** Fundamentals + news + broker grid for a ticker; optional panel chart / stacked layout. */
import type { ReactNode } from 'react';
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
import type { LayoutSlotId } from '../workspace/layoutStore';
import { coalesceQuoteOrder } from '../workspace/layoutStore';
import { useLayoutStore } from '../workspace/useLayoutStore';
import { useModuleVisibility } from '../workspace/useModuleVisibility';
import { useWorkspace } from '../workspace/WorkspaceContext';

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
  /** Which layout-store slot drives panel order (Phase 5). */
  layoutSlot?: LayoutSlotId;
  /** Five Pillars / sub-scores for this symbol when ranked on the watchlist. */
  watchlistEntry?: WatchlistEntry | null;
  /** Inserted immediately under Level 2 / Time & Sales (e.g. Stock View trade bar). */
  afterDepth?: ReactNode;
  /** Inserted immediately under the quote / fundamentals block (e.g. news bump). */
  afterQuote?: ReactNode;
  /** When true, skip the news block (parent renders it elsewhere, e.g. Stock View footer). */
  omitNews?: boolean;
}

export function TickerDetailContent({
  detail,
  selectedSymbol,
  hideHeader = false,
  showChart = false,
  layout = 'stack',
  layoutSlot = 'side_panel',
  watchlistEntry = null,
  afterDepth = null,
  afterQuote = null,
  omitNews = false,
}: Props) {
  const { discoveryProvider } = useWorkspace();
  const { isVisible } = useModuleVisibility();
  const { getOrder } = useLayoutStore();
  const depthSymbol = (selectedSymbol ?? detail.symbol).toUpperCase();
  const detailMatchesSelected =
    !selectedSymbol || detail.symbol.toUpperCase() === selectedSymbol.toUpperCase();
  const trade = detailMatchesSelected ? detail.snapshot?.latest_trade : undefined;
  const { lastUpdated } = computeQuoteMetrics(detail, discoveryProvider);
  const showQuote = isVisible('quote');
  const showNews = isVisible('news');
  const showCharts = isVisible('charts');
  const blockOrder = coalesceQuoteOrder(getOrder(layoutSlot));

  // Bind chart to selectedSymbol (not a stale detail.symbol) and skip live trades
  // until detail catches up to the open ticker.
  const chartEl =
    showChart && showCharts ? (
      <TickerChart
        symbol={depthSymbol}
        variant="panel"
        lastTrade={
          trade?.price != null
            ? {
                price: trade.price,
                timestamp: trade.timestamp ?? null,
                symbol: depthSymbol,
              }
            : undefined
        }
      />
    ) : null;

  const bottomStamp = lastUpdated ? (
    <div className="cq-timestamp cq-timestamp-bottom">
      Last updated on {fmtTimestamp(lastUpdated)}
    </div>
  ) : null;

  const depthEl = (
    <DepthTapePanel selectedSymbol={depthSymbol} detailSymbol={detail.symbol} />
  );

  const newsEl = showNews && !omitNews ? (
    <NewsPanel detail={detail} wrapped={layout === 'columns'} />
  ) : null;

  if (layout === 'columns') {
    const quoteCol = (
      <div className="cq-info-row cq-info-row--two" key="quote" data-layout-block="quote">
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
    );

    const nodes: ReactNode[] = [];
    for (const block of blockOrder) {
      if (block === 'charts') {
        nodes.push(
          <div key="charts" className="cq-col cq-col--chart" data-layout-block="charts">
            {chartEl}
          </div>,
        );
        nodes.push(<WatchlistStripPanel key="watchlist-strip" entry={watchlistEntry} />);
      } else if (block === 'depth_tape') {
        nodes.push(
          <div key="depth_tape" data-layout-block="depth_tape">
            {depthEl}
          </div>,
        );
        if (afterDepth) {
          nodes.push(
            <div key="after-depth" className="cq-after-depth" data-layout-block="after_depth">
              {afterDepth}
            </div>,
          );
        }
      } else if (block === 'news' && newsEl) {
        nodes.push(
          <div key="news" data-layout-block="news">
            {newsEl}
          </div>,
        );
      } else if (block === 'quote') {
        nodes.push(quoteCol);
        if (afterQuote) {
          nodes.push(
            <div key="after-quote" className="cq-after-quote" data-layout-block="after_quote">
              {afterQuote}
            </div>,
          );
        }
      }
    }

    return <div className="cq-root cq-root--stacked">{nodes}</div>;
  }

  const nodes: ReactNode[] = [];
  for (const block of blockOrder) {
    if (block === 'quote' && showQuote) {
      nodes.push(
        <div key="quote" data-layout-block="quote">
          <QuoteHeaderPanel detail={detail} hideHeader={hideHeader} />
        </div>,
      );
      if (afterQuote) {
        nodes.push(
          <div key="after-quote" className="cq-after-quote" data-layout-block="after_quote">
            {afterQuote}
          </div>,
        );
      }
    } else if (block === 'depth_tape') {
      nodes.push(
        <div key="depth_tape" data-layout-block="depth_tape">
          {depthEl}
        </div>,
      );
      if (afterDepth) {
        nodes.push(
          <div key="after-depth" className="cq-after-depth" data-layout-block="after_depth">
            {afterDepth}
          </div>,
        );
      }
    } else if (block === 'charts' && chartEl) {
      nodes.push(
        <div key="charts" data-layout-block="charts">
          {chartEl}
        </div>,
      );
    } else if (block === 'news' && newsEl) {
      nodes.push(
        <div key="news" data-layout-block="news">
          {newsEl}
        </div>,
      );
    }
  }
  nodes.push(<FundamentalsPanel key="fundamentals" detail={detail} variant="full" />);
  nodes.push(<DataSourcesPanel key="data-sources" />);
  if (bottomStamp) nodes.push(<div key="stamp">{bottomStamp}</div>);

  return <div className="cq-root">{nodes}</div>;
}
