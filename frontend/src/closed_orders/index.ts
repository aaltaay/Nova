/**
 * Closed Orders feature slice — public barrel (ADR 005).
 * Hosts mount via registry / TradingTab; do not deep-import internals elsewhere.
 */
export { ClosedOrdersPanel } from './ClosedOrdersPanel';
export { ClosedOrdersModule } from './ClosedOrdersModule';
export { ClosePositionButton } from './ClosePositionButton';
export { useClosedOrders } from './useClosedOrders';
export { buildMockClosedOrders } from './mockClosedOrders';
export { filterClosedOrders } from './filterClosedOrders';
export type { ClosedOrder, ClosedOrdersFilter } from './types';
