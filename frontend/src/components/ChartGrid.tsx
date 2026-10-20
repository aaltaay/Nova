/**
 * Multi-timeframe chart grid for Trader / Stock View (batch-warmed bars).
 * Live and recorded feeds share one layout. Only the bar warm and Clear all differ.
 */
import { memo, type ReactNode } from 'react';
import { ChartGridFrame } from './ChartGridLayout';
import { useChartFeed, useClearRecordedDrawings } from '../chart';
import type { RenderPaneOverlay } from '../chart';
import type { ChartGridPanel } from '../constantGroups/market_ui';

interface Props {
  symbol: string;
  /** Each pane follows the ticker stream itself (the Trader tab): a print draws the live candle without
   * rendering the grid (#707). */
  followTicker?: boolean;
  /** When false, panes pause refetch/resize (hidden Trader tab). */
  chartActive?: boolean;
  /** Drawn inside every pane (the Trader tab's stock read, ADR 036). */
  renderPaneOverlay?: RenderPaneOverlay;
  /** Extra switches on the desk toolbar. */
  toolbarExtra?: ReactNode;
  /** Defaults to the desk 2x2. A caller can pass a shorter list. */
  panels?: ChartGridPanel[];
}

/** Memoized with its panes (see TickerChart): the Trader page re-renders far more often than a chart changes. */
export const ChartGrid = memo(function ChartGrid(props: Props) {
  const feed = useChartFeed();
  if (feed.kind === 'recorded') return <RecordedChartGrid {...props} />;
  return <LiveChartGrid {...props} />;
});

function LiveChartGrid(props: Props) {
  return (
    <ChartGridFrame
      {...props}
      warm
      onClearDrawings={(symbol) => {
        void import('../chart/chartDrawingsStore').then(({ clearDrawings, drawingsKey }) => {
          clearDrawings(drawingsKey(symbol));
        });
      }}
    />
  );
}

function RecordedChartGrid(props: Props) {
  const clearRecorded = useClearRecordedDrawings();
  return (
    <ChartGridFrame
      {...props}
      warm={false}
      onClearDrawings={() => {
        clearRecorded();
      }}
    />
  );
}
