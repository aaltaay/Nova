import { lazy, memo, Suspense } from 'react';
import { TickerChartErrorBoundary } from '../components/TickerChartErrorBoundary';
import { useChartFeed } from './chartFeed';
import { RecordedPane } from './RecordedPane';
import type { ChartIndicatorId } from '../constantGroups/chart_api';
import type { ChartTradeUpdate, RenderPaneOverlay } from './types';

export type { ChartTradeUpdate } from './types';

const LivePane = lazy(() => import('./LivePane').then((mod) => ({ default: mod.LivePane })));

export interface TickerChartProps {
  symbol: string;
  lastTrade?: ChartTradeUpdate | null;
  /** Follow the ticker stream for the live candle instead of `lastTrade`: a print is drawn with no render
   * of the chart (the Trader grid, #707). */
  followTicker?: boolean;
  variant?: 'panel' | 'page' | 'grid';
  fixedTimeframe?: string;
  title?: string;
  subtitle?: string;
  /** Override default indicator toggles (e.g. grid 1m/5m start with MACD on). */
  initialIndicators?: ChartIndicatorId[];
  /**
   * Controlled indicators (Trader grid: the shared desk toolbar owns them).
   * When set, `initialIndicators` is ignored and toggles go through
   * `onIndicatorToggle`.
   */
  indicators?: ChartIndicatorId[];
  onIndicatorToggle?: (id: ChartIndicatorId) => void;
  /** Controlled drawing tool shared across grid panes (see useChartDrawingManager). */
  activeTool?: string | null;
  onActiveToolChange?: (tool: string | null) => void;
  /** One-line header, no per-pane toolbar (desk toolbar lives above the grid). */
  compactChrome?: boolean;
  /** Highlight as the pane the desk toolbar's indicator toggles target. */
  focused?: boolean;
  /** Pointer-down on this pane -- desk toolbar retargets to it. */
  onFocusPane?: () => void;
  /** When false, pause bar polling and resize work (hidden Trader tab). */
  chartActive?: boolean;
  /** Grid-local maximize (#113). Header ⛶ is fullscreen, not this flag. */
  maximized?: boolean;
  onMaximizeChange?: (next: boolean) => void;
  /** Double-click expands inside the 2x2; header ⛶ uses the Fullscreen API. */
  maximizeInGrid?: boolean;
  /** Bumps when the grid maximize layout flips so hidden siblings remeasure. */
  layoutEpoch?: string | null;
  /** What the page draws inside the pane (the Trader tab's stock read, ADR 036). */
  renderPaneOverlay?: RenderPaneOverlay;
}

/**
 * Memoized: the Trader page re-renders on every quote, and four panes drawing
 * again each time cost the desk its frame rate. A pane draws again when its own
 * props change (a trade, its indicators, the tool), never for its parent alone.
 */
export const TickerChart = memo(function TickerChart(props: TickerChartProps) {
  const feed = useChartFeed();
  return (
    <TickerChartErrorBoundary label={props.fixedTimeframe ?? props.title}>
      {feed.kind === 'recorded'
        ? <RecordedPane {...props} feed={feed} />
        : (
          <Suspense fallback={null}>
            <LivePane {...props} />
          </Suspense>
        )}
    </TickerChartErrorBoundary>
  );
});
