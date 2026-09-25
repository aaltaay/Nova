/** Public chart API — cross-feature imports must use this barrel (ADR 005). */

export { TickerChart } from './TickerChart';
export { parseBarsCoverage, setBars } from './barsStore';
export type { ChartPaneOverlayProps, ChartTradeUpdate, RenderPaneOverlay } from './types';
export { buildSeriesTimeIndex, nearestSeriesTime, toCanonicalTime } from './chartDrawingTime';
export { isFollowingRightEdge } from './chartViewportPaint';
export type { SeriesTimeIndex } from './chartDrawingTime';
