/**
 * Picks what the dashboard slot shows while Trader is not up: the dashboard
 * (children), or the Forex / Global / Market / Records / Account / Bots (Bots, LiveTrader Bots -- the TraderTV hosts' page --, Strategy
 * Bots) / Cryptos pages the nav rail routes to.
 */
import { lazy, Suspense, type ReactNode } from 'react';
import { TabLazyFallback } from '../components/TabLazyFallback';
import { useNavPage } from '../workspace/navRailStore';
import { RecordsPage } from './RecordsPage';

const AccountPage = lazy(() => import('./AccountPage').then((m) => ({ default: m.AccountPage })));
const BotsPage = lazy(() => import('../bot/BotsPage').then((m) => ({ default: m.BotsPage })));
const BotsGroupPage = lazy(() => import('../bot/BotsGroupPage').then((m) => ({ default: m.BotsGroupPage })));
const LiveTraderBotsPage = lazy(() =>
  import('../bot/LiveTraderBotsPage').then((m) => ({ default: m.LiveTraderBotsPage })),
);
const CryptosPage = lazy(() => import('../cryptos').then((m) => ({ default: m.CryptosPage })));
const MarketPage = lazy(() => import('../market_board').then((m) => ({ default: m.MarketPage })));
const GlobalPage = lazy(() => import('../global_board').then((m) => ({ default: m.GlobalPage })));
const ForexPage = lazy(() => import('../forex_board').then((m) => ({ default: m.ForexPage })));

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
  // Bots is a group (operator decision 2026-10-15): Bots itself is empty for now; Strategy Bots is the page that was Bots.
  if (page === 'bots') {
    return (
      <Suspense fallback={<TabLazyFallback />}>
        <BotsGroupPage />
      </Suspense>
    );
  }
  if (page === 'bots-live-trader') {
    return (
      <Suspense fallback={<TabLazyFallback />}>
        <LiveTraderBotsPage onOpenTrader={onOpenTrader} />
      </Suspense>
    );
  }
  if (page === 'bots-strategy') {
    return (
      <Suspense fallback={<TabLazyFallback />}>
        <BotsPage />
      </Suspense>
    );
  }
  return <>{children}</>;
}
