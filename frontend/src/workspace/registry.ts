/**
 * Module registry — catalog of Nova UI modules (tabs + panels).
 * TabNav / Modules menu / future ModuleHost read from here (Phase 4).
 */
import type { ComponentType } from 'react';
import { Level2Module } from '../modules/Level2Module';
import { TimeSalesModule } from '../modules/TimeSalesModule';
import { NewsPanel } from '../modules/NewsPanel';
import { QuoteHeaderPanel } from '../modules/QuoteHeaderPanel';
import { ChartsModule } from '../modules/ChartsModule';

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
  | 'catalysts'
  | 'hodMomo'
  | 'watchlist';

/** Tab ids — also the ActiveTab union used by Dashboard / TabNav. */
export const TAB_MODULE_IDS = [
  'dashboard',
  'gappers',
  'gainers',
  'losers',
  'afterhours',
  'catalysts',
  'hod_momo',
  'trading',
  'watchlist',
  'reports',
] as const;

export type ActiveTab = (typeof TAB_MODULE_IDS)[number];

export const DEFAULT_ACTIVE_TAB: ActiveTab = 'dashboard';

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
  /** Shown in the top TabNav when placement is `tab`. */
  showInTabNav?: boolean;
  countKey?: ModuleCountKey;
  badge?: string;
  defaultVisible?: boolean;
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const host = HostRenderedModule as ComponentType<any>;

export const NOVA_MODULES: readonly NovaModule[] = [
  {
    id: 'dashboard',
    title: 'Dashboard',
    component: host,
    feedDeps: ['none'],
    defaultPlacement: 'tab',
    showInTabNav: true,
  },
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
    id: 'trading',
    title: 'Trading',
    component: host,
    feedDeps: ['none'],
    defaultPlacement: 'tab',
    showInTabNav: true,
    badge: 'IBKR',
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
    id: 'reports',
    title: 'Reports',
    component: host,
    feedDeps: ['none'],
    defaultPlacement: 'tab',
    showInTabNav: true,
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
];

const byId = new Map(NOVA_MODULES.map(m => [m.id, m]));

export function getModule(id: string): NovaModule | undefined {
  return byId.get(id);
}

export function listModules(): readonly NovaModule[] {
  return NOVA_MODULES;
}

/** TabNav entries in registry order. */
export function listTabModules(): NovaModule[] {
  return NOVA_MODULES.filter(
    m => m.defaultPlacement === 'tab' && m.showInTabNav !== false,
  );
}

/** Runtime check — id is a registered tab module. */
export function isTabModuleId(id: string): id is ActiveTab {
  return (TAB_MODULE_IDS as readonly string[]).includes(id);
}
