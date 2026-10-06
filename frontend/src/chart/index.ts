/** Public chart API — cross-feature imports must use this barrel (ADR 005). */

export { TickerChart } from './TickerChart';
export { parseBarsCoverage, setBars } from './barsStore';
export type { ChartPaneOverlayProps, ChartTradeUpdate, RenderPaneOverlay } from './types';
export { buildSeriesTimeIndex, nearestSeriesTime, toCanonicalTime } from './chartDrawingTime';
export { isFollowingRightEdge } from './chartViewportPaint';
export { operatorOwnsView, watchOperatorView } from './operatorView';
export type { SeriesTimeIndex } from './chartDrawingTime';
export { EDGE_PRIORITY, claimEdge, edgeClaimed, edgeContents, subscribeEdge } from './edgeWords';
export type { EdgeReserve, EdgeWord } from './edgeWords';
export { publishPaneWords } from './paneWords';
export type { PaneWordRect } from './paneWords';
