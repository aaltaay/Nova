/**
 * Dock body for IBKR roster scanners (Gappers / Gainers / Losers / AH / Catalysts).
 */
import { ScannerTabPanels } from '../components/ScannerTabPanels';
import type { ScannerDockRows } from '../scanner/useScannerDockRows';
import type { ScannerDockRosterMode } from './scannerDockModes';

type Props = {
  mode: ScannerDockRosterMode;
  rows: ScannerDockRows;
  selectedSymbol: string | null;
  onSelect: (sym: string) => void;
  onOpenTrading: (sym: string) => void;
};

export function HodMomoDockRoster({
  mode,
  rows,
  selectedSymbol,
  onSelect,
  onOpenTrading,
}: Props) {
  return (
    <div className="hod-momo-dock__roster" data-testid="hod-momo-dock-roster">
      <ScannerTabPanels
        activeTab={mode}
        mode={rows.mode}
        health={rows.health}
        discoveryProvider={rows.discoveryProvider}
        gappers={rows.gappers}
        gainers={rows.gainers}
        losers={rows.losers}
        afterhours={rows.afterhours}
        catalysts={rows.catalysts}
        watchlistEntries={rows.watchlistEntries}
        selectedSymbol={selectedSymbol}
        onSelect={onSelect}
        onOpenTrading={onOpenTrading}
        pricesStale={rows.pricesStale}
        flashSymbols={rows.flashSymbols}
        rowQuoteTs={rows.rowQuoteTs}
        nowSec={rows.nowSec}
        tableMeta={rows.tableMeta}
      />
    </div>
  );
}
