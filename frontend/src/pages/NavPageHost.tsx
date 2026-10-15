/**
 * Picks what the dashboard slot shows while Trader is not up: the dashboard
 * (children), or the Market / Records / Account / Bots / Cryptos / Followed traders pages the nav rail routes to.
 * The TraderTV LIVE (followed traders) page carries the Live Trader bots' panel at its top (ADR 055; ADR 044
 * amendment 2026-10-15): composed here, so neither feature imports the other.
 */
import { lazy, Suspense, type ReactNode } from 'react';
import { TabLazyFallback } from '../components/TabLazyFallback';
import { useNavPage } from '../workspace/navRailStore';
import { RecordsPage } from './RecordsPage';

const AccountPage = lazy(() => import('./AccountPage').then((m) => ({ default: m.AccountPage })));
const BotsPage = lazy(() => import('../bot/BotsPage').then((m) => ({ default: m.BotsPage })));
const CryptosPage = lazy(() => import('../cryptos').then((m) => ({ default: m.CryptosPage })));
const FollowedTradersPage = lazy(() =>
  import('../followed_traders').then((m) => ({ default: m.FollowedTradersPage })),
);
const LiveTradersPanel = lazy(() =>
  import('../bot/BotLiveTradersCard').then((m) => ({ default: m.BotLiveTradersCard })),
);
const MarketPage = lazy(() => import('../market_board').then((m) => ({ default: m.MarketPage })));

interface Props {
  onOpenTrader: (symbol: string) => void;
  children: ReactNode;
}

export function NavPageHost({ onOpenTrader, children }: Props) {
  const page = useNavPage();
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
  if (page === 'followed') {
    return (
      <Suspense fallback={<TabLazyFallback />}>
        <FollowedTradersPage
          onOpenTrader={onOpenTrader}
          top={
            <Suspense fallback={null}>
              <LiveTradersPanel />
            </Suspense>
          }
        />
      </Suspense>
    );
  }
  if (page === 'bots') {
    return (
      <Suspense fallback={<TabLazyFallback />}>
        <BotsPage />
      </Suspense>
    );
  }
  return <>{children}</>;
}
