/**
 * Picks what the dashboard slot shows while Trader is not up: the dashboard
 * (children), or the Desk / Records / Account / Bots pages the nav rail routes to.
 */
import { lazy, Suspense, type ReactNode } from 'react';
import { TabLazyFallback } from '../components/TabLazyFallback';
import { useNavPage } from '../workspace/navRailStore';
import { DeskPage } from './DeskPage';
import { RecordsPage } from './RecordsPage';

const AccountPage = lazy(() => import('./AccountPage').then((m) => ({ default: m.AccountPage })));
const BotsPage = lazy(() => import('../bot/BotsPage').then((m) => ({ default: m.BotsPage })));

interface Props {
  onOpenTrader: (symbol: string) => void;
  children: ReactNode;
}

export function NavPageHost({ onOpenTrader, children }: Props) {
  const page = useNavPage();
  if (page === 'desk') return <DeskPage />;
  if (page === 'records') return <RecordsPage onOpenTrader={onOpenTrader} />;
  if (page === 'account') {
    return (
      <Suspense fallback={<TabLazyFallback />}>
        <AccountPage onOpenTrader={onOpenTrader} />
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
