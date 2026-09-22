/**
 * Picks what the dashboard slot shows while Trader is not up: the dashboard
 * (children), or the Desk / Records pages the nav rail routes to.
 */
import type { ReactNode } from 'react';
import { useNavPage } from '../workspace/navRailStore';
import { DeskPage } from './DeskPage';
import { RecordsPage } from './RecordsPage';

interface Props {
  onOpenTrader: (symbol: string) => void;
  children: ReactNode;
}

export function NavPageHost({ onOpenTrader, children }: Props) {
  const page = useNavPage();
  if (page === 'desk') return <DeskPage />;
  if (page === 'records') return <RecordsPage onOpenTrader={onOpenTrader} />;
  return <>{children}</>;
}
