/**
 * Picks what the dashboard slot shows while Trader is not up: the dashboard
 * (children), or the Forex / Global / Market / Records / Account / Cryptos / Congress / TraderTV pages the nav rail
 * routes to. ADR 072 retired the Bots group; TraderTV is the hosts' page without the bots.
 */
import { lazy, Suspense, type ReactNode } from 'react';
import { TabLazyFallback } from '../components/TabLazyFallback';
import { useNavPage } from '../workspace/navRailStore';
import { RecordsPage } from './RecordsPage';

const AccountPage = lazy(() => import('./AccountPage').then((m) => ({ default: m.AccountPage })));
const TraderTvPage = lazy(() => import('./TraderTvPage').then((m) => ({ default: m.TraderTvPage })));
const CryptosPage = lazy(() => import('../cryptos').then((m) => ({ default: m.CryptosPage })));
const MarketPage = lazy(() => import('../market_board').then((m) => ({ default: m.MarketPage })));
const GlobalPage = lazy(() => import('../global_board').then((m) => ({ default: m.GlobalPage })));
const ForexPage = lazy(() => import('../forex_board').then((m) => ({ default: m.ForexPage })));
const CongressPage = lazy(() => import('../congress').then((m) => ({ default: m.CongressPage })));

interface Props {
  onOpenTrader: (symbol: string) => void;
  children: ReactNode;
}

export function NavPageHost({ onOpenTrader, children }: Props) {
  const page = useNavPage();
  if (page === 'forex') {
    return (
      <Suspense fallback={<TabLazyFallback />}>
        <ForexPage />
      </Suspense>
    );
  }
  if (page === 'global') {
    return (
      <Suspense fallback={<TabLazyFallback />}>
        <GlobalPage onOpenTrader={onOpenTrader} />
      </Suspense>
    );
  }
  if (page === 'market') {
    return (
      <Suspense fallback={<TabLazyFallback />}>
        <MarketPage onOpenTrader={onOpenTrader} />
      </Suspense>
    );
  }
  if (page === 'records') return <RecordsPage onOpenTrader={onOpenTrader} />;
  if (page === 'account') {
    return (
      <Suspense fallback={<TabLazyFallback />}>
        <AccountPage onOpenTrader={onOpenTrader} />
      </Suspense>
    );
  }
  if (page === 'cryptos') {
    return (
      <Suspense fallback={<TabLazyFallback />}>
        <CryptosPage onOpenTrader={onOpenTrader} />
      </Suspense>
    );
  }
  if (page === 'congress') {
    return (
      <Suspense fallback={<TabLazyFallback />}>
        <CongressPage onOpenTrader={onOpenTrader} />
      </Suspense>
    );
  }
  if (page === 'tradertv') {
    return (
      <Suspense fallback={<TabLazyFallback />}>
        <TraderTvPage onOpenTrader={onOpenTrader} />
      </Suspense>
    );
  }
  return <>{children}</>;
}
