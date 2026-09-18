/**
 * Module registry — catalog of Nova UI modules (tabs + panels).
 * Scanner side nav / Modules menu / future ModuleHost read from here (Phase 4).
 */
import type { ComponentType } from 'react';
import { ClosedOrdersModule } from '../closed_orders';
import {
  ChartsModule,
  Level2Module,
  NewsPanel,
  QuoteHeaderPanel,
  TimeSalesModule,
} from '../modules';
import { CLOSED_ORDERS_MODULE_ID, CLOSED_ORDERS_PANEL_TITLE } from '../constants';

/** Feed dependencies declared for honesty / future ModuleHost gating. */
export type FeedDep =
  | 'none'
  | 'scanner'
  | 'ibkr_depth'
  | 'ibkr_tape'
  | 'hod_momo'
  | 'watchlist'
  | 'news'
  | 'chart';

export type DefaultPlacement = 'tab' | 'side_panel' | 'stock_view';

export type ModuleCountKey =
  | 'gappers'
  | 'gainers'
  | 'losers'
  | 'afterhours'
  | 'volumeBoost'
  | 'largeCap'
  | 'earnings'
  | 'novaNews'
  | 'catalysts'
  | 'hodMomo'
  | 'runningUp'
  | 'watchlist';

/** Tab ids — also the ActiveTab union used by Dashboard / TabNav. */
export const TAB_MODULE_IDS = [
  'gappers',
  'gainers',
  'losers',
  'afterhours',
  'volume_boost',
  'large_cap',
  'earnings',
  'nova_news',
  'catalysts',
  'hod_momo',
  'running_up',
  'trading',
  'watchlist',
  'strategy',
  'reports',
] as const;

export type ActiveTab = (typeof TAB_MODULE_IDS)[number];

/** Scanner homepage — Gappers (Dashboard config tab removed; Settings owns config). */
export const DEFAULT_ACTIVE_TAB: ActiveTab = 'gappers';

/**
 * Tab modules that need Dashboard props are host-rendered (component is a stub).
 * Panel modules point at real mountable components.
 */
export function HostRenderedModule() {
  return null;
}

export type NovaModule = {
  id: string;
  title: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  component: ComponentType<any>;
  feedDeps: readonly FeedDep[];
  defaultPlacement: DefaultPlacement;
  /** Shown in the scanner left rail when placement is `tab`. */
  showInTabNav?: boolean;
  countKey?: ModuleCountKey;
  badge?: string;
  defaultVisible?: boolean;
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const host = HostRenderedModule as ComponentType<any>;

export const NOVA_MODULES: readonly NovaModule[] = [
  {
    id: 'gappers',
    title: 'Gappers',
    component: host,
    feedDeps: ['scanner'],
    defaultPlacement: 'tab',
    showInTabNav: true,
    countKey: 'gappers',
  },
  {
    id: 'gainers',
    title: 'Gainers',
    component: host,
    feedDeps: ['scanner'],
    defaultPlacement: 'tab',
    showInTabNav: true,
    countKey: 'gainers',
  },
  {
    id: 'losers',
    title: 'Losers',
    component: host,
    feedDeps: ['scanner'],
    defaultPlacement: 'tab',
    showInTabNav: true,
    countKey: 'losers',
  },
  {
    id: 'afterhours',
    title: 'After Hours',
    component: host,
    feedDeps: ['scanner'],
    defaultPlacement: 'tab',
    showInTabNav: true,
    countKey: 'afterhours',
  },
  {
    id: 'volume_boost',
    title: 'Volume boost',
    component: host,
    // Derived from existing L1 day-volume -- not a /ws/scanner roster and
    // not a new reqMktData line (single-market-data-feed.mdc rule 12).
    feedDeps: ['none'],
    defaultPlacement: 'tab',
    showInTabNav: true,
    countKey: 'volumeBoost',
  },
  {
    id: 'large_cap',
    title: 'Large Cap',
    component: host,
    feedDeps: ['scanner'],
    defaultPlacement: 'tab',
    showInTabNav: true,
    countKey: 'largeCap',
  },
  {
    id: 'earnings',
    title: 'Earnings',
    component: host,
    // Finnhub calendar metadata -- not an IBKR scanner lease, no /ws/scanner
    // price stream (single-market-data-feed.mdc). Prices chip must not claim
    // this tab is covered by that feed.
    feedDeps: ['none'],
    defaultPlacement: 'tab',
    showInTabNav: true,
    countKey: 'earnings',
  },
  {
    id: 'nova_news',
    title: 'Nova News',
    component: host,
    // AI-in-trading headline desk -- not IBKR prices, not HOD.
    feedDeps: ['news'],
    defaultPlacement: 'tab',
    showInTabNav: true,
    countKey: 'novaNews',
  },
  {
    id: 'catalysts',
    title: 'Catalysts',
    component: host,
    feedDeps: ['scanner'],
    defaultPlacement: 'tab',
    showInTabNav: true,
    countKey: 'catalysts',
  },
  {
    id: 'hod_momo',
    title: 'HOD Momo',
    component: host,
    feedDeps: ['hod_momo'],
    defaultPlacement: 'tab',
    showInTabNav: true,
    countKey: 'hodMomo',
  },
  {
    id: 'running_up',
    title: 'Running Up',
    component: host,
    feedDeps: ['hod_momo'],
    defaultPlacement: 'tab',
    showInTabNav: true,
    countKey: 'runningUp',
  },
  {
    id: 'trading',
    title: 'Account',
    component: host,
    feedDeps: ['none'],
    defaultPlacement: 'tab',
    // Header control next to Today (Live) — not a scanner tab-bar entry.
    showInTabNav: false,
  },
  {
    id: 'watchlist',
    title: 'Watchlist',
    component: host,
    feedDeps: ['watchlist'],
    defaultPlacement: 'tab',
    showInTabNav: true,
    countKey: 'watchlist',
  },
  {
    id: 'strategy',
    title: 'Strategy',
    component: host,
    feedDeps: ['none'],
    defaultPlacement: 'tab',
    showInTabNav: true,
  },
  {
    id: 'reports',
    title: 'Reports',
    component: host,
    feedDeps: ['none'],
    defaultPlacement: 'tab',
    // Nested under Account (header) — not a top-level tab.
    showInTabNav: false,
  },
  {
    id: 'level2',
    title: 'Level 2',
    component: Level2Module,
    feedDeps: ['ibkr_depth'],
    defaultPlacement: 'side_panel',
  },
  {
    id: 'tape',
    title: 'Time & Sales',
    component: TimeSalesModule,
    feedDeps: ['ibkr_tape'],
    defaultPlacement: 'side_panel',
  },
  {
    id: 'news',
    title: 'News',
    component: NewsPanel,
    feedDeps: ['news'],
    defaultPlacement: 'side_panel',
  },
  {
    id: 'quote',
    title: 'Quote',
    component: QuoteHeaderPanel,
    feedDeps: ['none'],
    defaultPlacement: 'side_panel',
  },
  {
    id: 'charts',
    title: 'Charts',
    component: ChartsModule,
    feedDeps: ['chart'],
    defaultPlacement: 'stock_view',
  },
  {
    id: CLOSED_ORDERS_MODULE_ID,
    title: CLOSED_ORDERS_PANEL_TITLE,
    component: ClosedOrdersModule,
    feedDeps: ['none'],
    /** Account overview host; Modules menu hide/show; future drag-drop slot. */
    defaultPlacement: 'side_panel',
    defaultVisible: true,
  },
];

const byId = new Map(NOVA_MODULES.map(m => [m.id, m]));

export function getModule(id: string): NovaModule | undefined {
  return byId.get(id);
}

export function listModules(): readonly NovaModule[] {
  return NOVA_MODULES;
}

/** Scanner side-nav entries in registry order. */
export function listTabModules(): NovaModule[] {
  return NOVA_MODULES.filter(
    m => m.defaultPlacement === 'tab' && m.showInTabNav !== false,
  );
}

/** Runtime check — id is a registered tab module. */
export function isTabModuleId(id: string): id is ActiveTab {
  return (TAB_MODULE_IDS as readonly string[]).includes(id);
}

/** Header "Prices" chip reflects /ws/scanner price_patch freshness — scanner tabs only. */
export function tabUsesScannerPricePatch(id: string): boolean {
  const mod = getModule(id);
  return mod?.feedDeps.includes('scanner') ?? false;
}
