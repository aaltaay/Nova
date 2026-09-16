/**
 * Compatibility barrel for Nova UI constants (Phase 3).
 *
 * Facade owner: Pattern-Driven Architecture Phase 3.
 * Removal criterion: no new definitions here; callers import
 * `constantGroups/*` or feature-local constants, or barrel stays thin.
 */

export * from './constantGroups/market_ui';
export * from './constantGroups/chart_api';
export * from './constantGroups/trader_view';
export * from './constantGroups/features';
export * from './constantGroups/api_auth';
export * from './constantGroups/theme';
export * from './constantGroups/ux';
export * from './constantGroups/global_bar';
export * from './constantGroups/halt_eta';
export * from './constantGroups/trade_defaults';
export * from './constantGroups/news_junk';
