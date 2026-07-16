/**
 * Strangler facade — implementation lives in ``chart/TickerChart``.
 *
 * Facade owner: close-remediation Phase 5.
 * Removal criterion: no production imports of ``../TickerChart`` /
 * ``./TickerChart`` outside ``chart/``; callers use ``from '../chart'``.
 */
export { TickerChart, type ChartTradeUpdate } from './chart/TickerChart';
